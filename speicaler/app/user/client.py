import asyncio
import json
import re
import tempfile
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telethon import TelegramClient, events, functions, types

from app.core.config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from app.core.database import *
from app.core.ai import ask_gemini, parse_request
from app.user.moderation import check_muted, mute_in_chat, unmute_in_chat, is_muted_in_chat

client = TelegramClient("special_user", int(API_ID), API_HASH)
USER_CLIENTS = {}
CLIENT_BOT_IDS = {}
ACTIVE_CLIENT = ContextVar("special_active_client", default=None)
ACTIVE_BOT_USER = ContextVar("special_active_bot_user", default=None)
bot = Bot(token=BOT_TOKEN)

ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROOT = ROOT / "storage" / "media"
PROFILE_ROOT = ROOT / "storage" / "profile_mimic"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
PROFILE_BACKUP = PROFILE_ROOT / "backup.json"

def active_client():
    return ACTIVE_CLIENT.get() or client

def set_active_client(user_client, bot_user_id=None):
    ACTIVE_CLIENT.set(user_client)
    if bot_user_id is not None:
        ACTIVE_BOT_USER.set(int(bot_user_id))
        set_active_profile(int(bot_user_id))

def active_bot_user_id():
    return ACTIVE_BOT_USER.get()

def profile_root_for_current():
    uid = active_bot_user_id()
    root = PROFILE_ROOT / str(uid) if uid is not None else PROFILE_ROOT / "owner"
    root.mkdir(parents=True, exist_ok=True)
    return root

def profile_backup_for_current():
    return profile_root_for_current() / "backup.json"

def media_root_for_current():
    uid = active_bot_user_id()
    root = MEDIA_ROOT / str(uid) if uid is not None else MEDIA_ROOT / "owner"
    root.mkdir(parents=True, exist_ok=True)
    return root

RANGE_STARTS = {}
IMPORT_LOCK = asyncio.Lock()
WATCHDOG_LOCK = asyncio.Lock()


def media_type(message):
    if not message or not message.media:
        return None
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.sticker:
        return "sticker"
    if message.gif:
        return "gif"
    if message.voice:
        return "voice"
    if message.audio:
        return "audio"
    return "file"


def has_link(text):
    return bool(text and re.search(r"https?://|t\.me/", text, re.I))


async def archive_media(event, user_id, direction):
    if not event.message or not event.message.media:
        return None
    folder = media_root_for_current() / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return await event.download_media(file=str(folder / f"{direction}_{event.id}"))
    except Exception:
        return None


async def archive_import_media(message, user_id, direction):
    if not message or not message.media:
        return None
    folder = media_root_for_current() / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return await message.download_media(file=str(folder / f"{direction}_{message.id}"))
    except Exception:
        return None


async def send_text_chunks(text):
    if not ADMIN_ID:
        return
    for i in range(0, len(text or ""), 4000):
        await bot.send_message(int(ADMIN_ID), text[i:i + 4000])


async def save_replied_media(event, replied, sender):
    if not replied or not replied.media or not ADMIN_ID:
        return False
    name = getattr(sender, "first_name", None) or getattr(sender, "last_name", None) or "مستخدم"
    username = getattr(sender, "username", None)
    url = f"https://t.me/{username}" if username else f"tg://user?id={sender.id}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 فتح المستخدم", url=url)]])
    caption = f"📥 تم حفظ وسائط من الخاص\n\n👤 الاسم: {name}\n🆔 ID: {sender.id}\n🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n🕐 التاريخ: {replied.date}"
    temp_dir = Path(tempfile.mkdtemp(prefix="special_reply_media_"))
    try:
        path = await replied.download_media(file=str(temp_dir / f"media_{replied.id}"))
        if not path:
            return False
        f = FSInputFile(path)
        if replied.photo:
            await bot.send_photo(int(ADMIN_ID), f, caption=caption, reply_markup=markup)
        elif replied.video:
            await bot.send_video(int(ADMIN_ID), f, caption=caption, reply_markup=markup)
        elif replied.voice:
            await bot.send_voice(int(ADMIN_ID), f, caption=caption, reply_markup=markup)
        elif replied.audio:
            await bot.send_audio(int(ADMIN_ID), f, caption=caption, reply_markup=markup)
        else:
            await bot.send_document(int(ADMIN_ID), f, caption=caption, reply_markup=markup)
        return True
    except Exception as exc:
        add_log("operation_log", "reply_media_save_failed", f"{type(exc).__name__}: {exc}")
        return False
    finally:
        for item in temp_dir.iterdir():
            if item.is_file():
                item.unlink(missing_ok=True)
        temp_dir.rmdir()


def _profile_name(user):
    if hasattr(user, "title") and getattr(user, "title", None):
        return str(user.title), ""
    return ((getattr(user, "first_name", None) or "").strip(), (getattr(user, "last_name", None) or "").strip())


def _load_profile_backup():
    backup_path = profile_backup_for_current()
    if not backup_path.exists():
        return None
    try:
        return json.loads(backup_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_profile_backup(data):
    profile_backup_for_current().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def _delete_current_profile_photos():
    try:
        me = await active_client().get_me()
        photos = await active_client().get_profile_photos(me, limit=100)
        if photos:
            await active_client()(functions.photos.DeletePhotosRequest(id=list(photos)))
    except Exception as exc:
        add_log("operation_log", "profile_photo_delete_failed", type(exc).__name__)


async def _backup_current_profile():
    existing = _load_profile_backup()
    if existing and existing.get("active"):
        return existing
    me = await active_client().get_me()
    first, last = _profile_name(me)
    original_about = await _fresh_about(me)
    # Never overwrite the real bio backup with an empty value when Telegram
    # failed to return the current bio. The mimic operation must abort instead.
    if original_about is None:
        raise RuntimeError("تعذر قراءة البايو الأصلي للحساب — تم إيقاف التقليد حتى لا يضيع")
    backup = {"active": True, "first_name": first, "last_name": last, "about": original_about, "photo": None, "created_at": datetime.now(timezone.utc).isoformat(), "backup_version": 3}
    photos = await active_client().get_profile_photos(me, limit=1)
    if photos:
        photo_path = profile_root_for_current() / "original_profile_photo"
        downloaded = await active_client().download_media(photos[0], file=str(photo_path))
        if downloaded:
            backup["photo"] = str(downloaded)
    _save_profile_backup(backup)
    return backup


def _numeric_sender_id(message):
    sender_id = getattr(message, "sender_id", None) if message else None
    if sender_id is None:
        return None
    value = getattr(sender_id, "user_id", sender_id)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _resolve_reply_user(event):
    """Resolve a replied-to user's numeric ID even when Telegram omits the sender entity."""
    reply = None
    try:
        if event.is_reply:
            reply = await event.get_reply_message()
    except Exception:
        reply = None

    if reply:
        try:
            sender = await reply.get_sender()
            if sender and getattr(sender, "id", None) is not None:
                return sender, int(sender.id)
        except Exception:
            pass
        sender_id = _numeric_sender_id(reply)
        if sender_id is not None:
            return None, sender_id

    # Fallback to the raw reply_to message ID. This also covers channel/group
    # updates where Telethon does not expose event.is_reply consistently.
    reply_to_id = getattr(event, "reply_to_msg_id", None)
    if reply_to_id is None:
        reply_to = getattr(event, "reply_to", None)
        reply_to_id = getattr(reply_to, "reply_to_msg_id", None)
    if reply_to_id is not None:
        try:
            reply = await active_client().get_messages(event.chat_id, ids=int(reply_to_id))
            if reply:
                try:
                    sender = await reply.get_sender()
                    if sender and getattr(sender, "id", None) is not None:
                        return sender, int(sender.id)
                except Exception:
                    pass
                sender_id = _numeric_sender_id(reply)
                if sender_id is not None:
                    return None, sender_id
        except Exception:
            pass
    return None, None


async def _resolve_target(event):
    sender, sender_id = await _resolve_reply_user(event)
    if sender:
        return sender
    if sender_id is not None:
        try:
            return await active_client().get_entity(sender_id)
        except Exception:
            return type("ReplyTarget", (), {"id": sender_id})()
    match = re.search(r"@([A-Za-z0-9_]{3,32})", event.raw_text or "")
    if match:
        try:
            return await active_client().get_entity(match.group(1))
        except Exception:
            return None
    return None


async def _fresh_about(target):
    try:
        if isinstance(target, types.User):
            full = await active_client()(functions.users.GetFullUserRequest(target))
            return getattr(full.full_user, "about", None) or ""
        if isinstance(target, types.Channel):
            full = await active_client()(functions.channels.GetFullChannelRequest(target))
            return getattr(full.full_chat, "about", None) or ""
        if isinstance(target, types.Chat):
            full = await active_client()(functions.messages.GetFullChatRequest(target.id))
            return getattr(full.full_chat, "about", None) or ""
    except Exception as exc:
        add_log("operation_log", "profile_about_read_failed", f"{type(exc).__name__}: {exc}")
        return None
    return getattr(target, "about", None)


async def _available_similar_username(target_username: str):
    if not target_username:
        return None
    base = re.sub(r"[^A-Za-z0-9_]", "", target_username)[:28]
    candidates = [base, f"{base}_"[:32]]
    for i in range(1, 21):
        suffix = str(i)
        candidates.append((base[:32-len(suffix)] + suffix)[:32])
    seen = set()
    for candidate in candidates:
        candidate = candidate.strip("_")
        if not candidate or candidate.lower() in seen or len(candidate) < 5:
            continue
        seen.add(candidate.lower())
        try:
            checked = await active_client()(functions.account.CheckUsernameRequest(username=candidate))
            if checked:
                return candidate
        except Exception:
            continue
    return None


async def _apply_mimic_target(target):
    refreshed = await active_client().get_entity(target.id)
    settings = {
        "mimic_enabled": get_setting("mimic_enabled", "1"),
        "mimic_name": get_setting("mimic_name", "1"),
        "mimic_photo": get_setting("mimic_photo", "1"),
        "mimic_bio": get_setting("mimic_bio", "1"),
    }
    if settings["mimic_enabled"] != "1":
        raise RuntimeError("التقليد معطل من إعدادات البوت")

    first, last = _profile_name(refreshed)
    about = await _fresh_about(refreshed) if settings["mimic_bio"] == "1" else None
    kwargs = {}
    if settings["mimic_name"] == "1":
        kwargs.update(first_name=first or "Special", last_name=last)
    if settings["mimic_bio"] == "1" and about is not None:
        kwargs["about"] = about
    if kwargs:
        await active_client()(functions.account.UpdateProfileRequest(**kwargs))

    if settings["mimic_photo"] == "1":
        photos = await active_client().get_profile_photos(refreshed, limit=1)
        await _delete_current_profile_photos()
        if photos:
            temp_dir = Path(tempfile.mkdtemp(prefix="special_mimic_"))
            try:
                path = await active_client().download_media(photos[0], file=str(temp_dir / "latest_profile"))
                if path:
                    uploaded = await active_client().upload_file(path)
                    await active_client()(functions.photos.UploadProfilePhotoRequest(file=uploaded))
            finally:
                for item in temp_dir.iterdir():
                    if item.is_file():
                        item.unlink(missing_ok=True)
                temp_dir.rmdir()

async def mimic_user(target):
    if get_setting("mimic_enabled", "1") != "1":
        raise RuntimeError("التقليد معطل من إعدادات البوت")
    backup = await _backup_current_profile()
    backup.update({"mimic_target_id": int(target.id), "mimic_target_type": target.__class__.__name__, "active": True})
    _save_profile_backup(backup)
    await _apply_mimic_target(target)
    add_log("operation_log", "profile_mimic_started", f"target={target.id}")


async def refresh_mimic_profile():
    backup = _load_profile_backup()
    if not backup or not backup.get("active") or not backup.get("mimic_target_id"):
        return False
    target = await active_client().get_entity(int(backup["mimic_target_id"]))
    await _apply_mimic_target(target)
    backup["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    _save_profile_backup(backup)
    return True


async def restore_profile():
    backup = _load_profile_backup()
    if not backup or not backup.get("active"):
        return False
    await active_client()(functions.account.UpdateProfileRequest(first_name=backup.get("first_name") or "Special", last_name=backup.get("last_name") or "", about=backup.get("about") or ""))
    await _delete_current_profile_photos()
    if backup.get("photo") and Path(backup["photo"]).exists():
        uploaded = await active_client().upload_file(backup["photo"])
        await active_client()(functions.photos.UploadProfilePhotoRequest(file=uploaded))
    backup["active"] = False
    _save_profile_backup(backup)
    return True




async def is_special_or_bot_user(entity, special_bot_id=None):
    """Return True for Telegram bot accounts, including Special itself."""
    if not entity:
        return False
    if getattr(entity, "bot", False):
        return True
    if getattr(entity, "deleted", False):
        return True
    if special_bot_id is not None and getattr(entity, "id", None) == special_bot_id:
        return True
    return False


def _dialog_last_seen(dialog):
    value = getattr(dialog, "date", None)
    return value.isoformat() if value is not None else None


async def sync_all_private_users():
    """Sync private people once, preserving Telegram dialog recency order."""
    added = updated = skipped = 0
    me = await active_client().get_me()
    special_bot_id = None
    try:
        special_bot_id = int((await bot.get_me()).id)
    except Exception:
        pass

    async for dialog in active_client().iter_dialogs():
        if not dialog.is_user:
            continue
        user = dialog.entity
        if user.id == me.id or await is_special_or_bot_user(user, special_bot_id):
            skipped += 1
            continue
        name = getattr(user, "first_name", None) or getattr(user, "last_name", None) or "مستخدم"
        exists = get_private_chat(user.id)
        upsert_private_chat(
            user.id, getattr(user, "username", None), name,
            is_bot=False, is_deleted_user=False, last_seen=_dialog_last_seen(dialog)
        )
        if exists:
            updated += 1
        else:
            added += 1
    add_log("operation_log", "sync_private_users", f"added={added},updated={updated},skipped={skipped}")
    return {"added": added, "updated": updated, "skipped": skipped}


async def import_all_private_history():
    """Import private history in one dialog pass with batched DB writes."""
    async with IMPORT_LOCK:
        chats = messages = skipped = 0
        me = await active_client().get_me()
        special_bot_id = None
        try:
            special_bot_id = int((await bot.get_me()).id)
        except Exception:
            pass

        async for dialog in active_client().iter_dialogs():
            if not dialog.is_user:
                continue
            entity = dialog.entity
            if entity.id == me.id or await is_special_or_bot_user(entity, special_bot_id):
                skipped += 1
                continue

            chats += 1
            user_id = int(entity.id)
            name = getattr(entity, "first_name", None) or getattr(entity, "last_name", None) or "مستخدم"
            dialog_last_seen = _dialog_last_seen(dialog)
            upsert_private_chat(
                user_id, getattr(entity, "username", None), name,
                is_bot=False, is_deleted_user=False, last_seen=dialog_last_seen
            )

            batch = []
            async for msg in active_client().iter_messages(entity, reverse=True):
                batch.append((
                    int(msg.id), user_id, user_id,
                    "outgoing" if getattr(msg, "out", False) else "incoming",
                    msg.raw_text, media_type(msg),
                    None,
                    str(msg.date),
                ))
                if len(batch) >= 100:
                    inserted, inserted_rows = insert_messages_batch(batch)
                    messages += inserted
                    skipped += len(batch) - inserted
                    increment_stats_bulk(user_id, inserted_rows)
                    batch.clear()
            if batch:
                inserted, inserted_rows = insert_messages_batch(batch)
                messages += inserted
                skipped += len(batch) - inserted
                increment_stats_bulk(user_id, inserted_rows)

        dedupe_messages()
        add_log("operation_log", "private_history_import", f"chats={chats},new={messages},skipped={skipped}")
        return {"chats": chats, "messages": messages, "skipped": skipped}


async def _send_edit_notification(sender, old_text, new_text, message_id):
    if not ADMIN_ID or get_setting("notify_edited", "1") != "1":
        return
    if getattr(sender, "bot", False) or getattr(sender, "deleted", False):
        return
    name = getattr(sender, "first_name", None) or getattr(sender, "last_name", None) or "مستخدم"
    username = getattr(sender, "username", None)
    url = f"https://t.me/{username}" if username else f"tg://user?id={sender.id}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 فتح حساب الشخص", url=url)]])
    body = f"✏️ تم تعديل رسالة في الخاص\n\n👤 الاسم: {name}\n🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n🆔 ID: {sender.id}\n🧾 Message ID: {message_id}\n\nقبل:\n{old_text or '[بدون نص]'}\n\nبعد:\n{new_text or '[بدون نص]'}"
    try:
        await bot.send_message(int(ADMIN_ID), body[:3900], reply_markup=markup)
    except Exception:
        pass


async def _send_delete_notification(row):
    if not ADMIN_ID or get_setting("notify_deleted", "1") != "1":
        return
    username = row["username"] if "username" in row.keys() else None
    url = f"https://t.me/{username}" if username else f"tg://user?id={row['user_id']}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 فتح حساب الشخص", url=url)]])
    body = f"🗑️ تم حذف رسالة من الخاص\n\n👤 الاسم: {row['display_name'] or 'مستخدم'}\n🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n🆔 ID: {row['user_id']}\n\n💬 {row['text'] or '[' + (row['media_type'] or 'وسائط') + ']'}"
    try:
        await bot.send_message(int(ADMIN_ID), body[:3900], reply_markup=markup)
    except Exception:
        pass


async def _delete_range_exact(chat_id, start_id, end_id, control_ids):
    if end_id < start_id:
        raise ValueError("invalid_range")
    entity = await active_client().get_entity(chat_id)
    if not isinstance(entity, types.User):
        me = await active_client().get_me()
        try:
            perms = await active_client().get_permissions(entity, me)
        except Exception as exc:
            raise PermissionError("delete_messages") from exc
        if not getattr(perms, "is_creator", False) and not getattr(perms, "delete_messages", False):
            raise PermissionError("delete_messages")
    actual = []
    async for message in active_client().iter_messages(chat_id, min_id=start_id - 1, max_id=end_id + 1, reverse=True):
        if message.id >= start_id and message.id <= end_id:
            actual.append(int(message.id))
    ordered = sorted(set(actual).union(int(x) for x in control_ids if x))
    deleted = 0
    for offset in range(0, len(ordered), 100):
        batch = ordered[offset:offset + 100]
        try:
            await active_client().delete_messages(chat_id, batch)
            deleted += len(batch)
        except Exception:
            for mid in batch:
                try:
                    result = await active_client().delete_messages(chat_id, [mid])
                    if result:
                        deleted += 1
                except Exception:
                    pass
    return deleted


async def refresh_special():
    init_database()
    dedupe_messages()
    sync_result = await sync_all_private_users()
    if not active_client().is_connected():
        await active_client().connect()
    refreshed = await refresh_mimic_profile()
    return {"mimic_refreshed": refreshed, "private_sync": sync_result, "connected": active_client().is_connected()}


@client.on(events.NewMessage(incoming=True))
async def incoming(event):
    set_active_client(event.client, CLIENT_BOT_IDS.get(id(event.client), int(ADMIN_ID) if ADMIN_ID else None))
    sender = await event.get_sender()
    if not sender:
        return
    # Ignore bots completely for private edit/AI workflows.
    if getattr(sender, "bot", False):
        return

    if event.is_private:
        name = getattr(sender, "first_name", None) or getattr(sender, "last_name", None) or "مستخدم"
        upsert_private_chat(sender.id, getattr(sender, "username", None), name, is_bot=False, is_deleted_user=getattr(sender, "deleted", False))
        ai_ok, ai_prompt = parse_request(event.raw_text)
        if ai_ok and ai_prompt:
            try:
                answer = await ask_gemini(ai_prompt)
                if answer:
                    await event.reply(answer[:4000])
                    add_ai_log("user_account", sender.id, name, getattr(sender, "username", None), event.chat_id, "private", ai_prompt, answer)
            except Exception as exc:
                add_log("operation_log", "gemini_failed", f"{type(exc).__name__}: {exc}")
            return

        inserted_id, inserted = insert_message_once(
            event.id, sender.id, event.chat_id, "incoming", event.raw_text,
            media_type(event.message), await archive_media(event, sender.id, "in") if event.message and event.message.media else None,
            str(event.date)
        )
        if inserted:
            increment_stats(sender.id, media_type(event.message), has_link(event.raw_text))
        if check_muted(sender.id) or is_muted_in_chat(event.chat_id, sender.id):
            try:
                await event.delete()
                mark_message_deleted(event.id, event.chat_id)
            except Exception:
                add_log("operation_log", "mute_delete_failed", f"chat={event.chat_id},user={sender.id}")
        return

    ai_ok, ai_prompt = parse_request(event.raw_text)
    if ai_ok and ai_prompt:
        try:
            answer = await ask_gemini(ai_prompt)
            if answer:
                await event.reply(answer[:4000])
                chat = await event.get_chat()
                add_ai_log("user_account", getattr(sender, "id", None), getattr(sender, "title", None) or getattr(sender, "first_name", None) or "مستخدم", getattr(sender, "username", None), event.chat_id, chat.__class__.__name__, ai_prompt, answer)
        except Exception as exc:
            add_log("operation_log", "gemini_failed", f"{type(exc).__name__}: {exc}")
        return

    if is_muted_in_chat(event.chat_id, sender.id):
        try:
            await event.delete()
        except Exception:
            add_log("operation_log", "group_mute_delete_failed", f"chat={event.chat_id},user={sender.id}")


@client.on(events.MessageEdited(incoming=True))
async def incoming_edit(event):
    set_active_client(event.client, CLIENT_BOT_IDS.get(id(event.client), int(ADMIN_ID) if ADMIN_ID else None))
    if not event.is_private:
        return
    sender = await event.get_sender()
    if not sender or getattr(sender, "bot", False) or getattr(sender, "deleted", False):
        return
    row = get_message_record(event.id, event.chat_id, "incoming")
    old_text = row["text"] if row else ""
    if not row:
        return
    if mark_message_edited(event.id, event.chat_id, "incoming", event.raw_text):
        await _send_edit_notification(sender, old_text, event.raw_text, event.id)


@client.on(events.MessageDeleted)
async def deleted_event(event):
    set_active_client(event.client, CLIENT_BOT_IDS.get(id(event.client), int(ADMIN_ID) if ADMIN_ID else None))
    # Telegram/Telethon does not provide a reliable private-chat peer for bare
    # delete updates. Do not infer a private deletion from message ID alone;
    # private deletions are audited per-chat below to avoid false notifications.
    chat_id = getattr(event, "chat_id", None)
    if chat_id is None:
        return
    ids = list(getattr(event, "deleted_ids", []) or getattr(event, "message_ids", []) or [])
    if not ids:
        return
    rows = get_messages_by_telegram_ids(ids, chat_id=chat_id)
    for row in rows:
        if row["direction"] != "incoming":
            mark_message_deleted(row["telegram_message_id"], row["chat_id"], row["direction"])


async def audit_recent_private_deletions(limit_chats=25, messages_per_chat=80):
    """Check stored incoming private messages chat-by-chat before notifying.
    This avoids false positives caused by Telegram delete updates without peer context.
    """
    rows = list_private_chats()[:limit_chats]
    for person in rows:
        user_id = int(person["user_id"])
        try:
            stored = list_recent_incoming_messages(user_id, messages_per_chat)
            ids = [int(r["telegram_message_id"]) for r in stored]
            if not ids:
                continue
            current = await active_client().get_messages(user_id, ids=ids)
            current_ids = {int(m.id) for m in current if m is not None}
            for row in stored:
                mid = int(row["telegram_message_id"])
                if mid not in current_ids and row["deleted_at"] is None:
                    if message_marked_deleted(mid, user_id, "incoming"):
                        await _send_delete_notification(row)
        except Exception as exc:
            add_log("operation_log", "private_delete_audit_failed", f"user={user_id}:{type(exc).__name__}")


@client.on(events.NewMessage(outgoing=True))
async def outgoing(event):
    set_active_client(event.client, CLIENT_BOT_IDS.get(id(event.client), int(ADMIN_ID) if ADMIN_ID else None))
    target = await event.get_chat()
    text = (event.raw_text or "").strip()
    lower = text.lower()

    if event.is_private:
        name = getattr(target, "first_name", None) or getattr(target, "last_name", None) or "مستخدم"
        upsert_private_chat(target.id, getattr(target, "username", None), name)
        media_path = await archive_media(event, target.id, "out") if event.message and event.message.media else None
        inserted_id, inserted = insert_message_once(event.id, target.id, event.chat_id, "outgoing", event.raw_text, media_type(event.message), media_path, str(event.date))
        if inserted:
            increment_stats(target.id, media_type(event.message), has_link(event.raw_text))
        if event.is_reply:
            replied = await event.get_reply_message()
            if replied and replied.media:
                await save_replied_media(event, replied, target)

    if lower in {"/بداية الحذف", "بداية الحذف", "/بداية", "بداية"}:
        if not event.is_reply:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        replied = await event.get_reply_message()
        if not replied:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        RANGE_STARTS[event.chat_id] = {"target_id": replied.id, "control_id": event.id}
        await event.edit("✅ تم تحديد بداية الحذف")
        return

    if lower in {"/نهاية الحذف", "نهاية الحذف", "/نهاية", "نهاية"}:
        if not event.is_reply:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        replied = await event.get_reply_message()
        if not replied:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        marker = RANGE_STARTS.get(event.chat_id)
        if not marker:
            await event.edit("❌ فشلت العملية يجب تحديد رسالة البداية أولًا")
            return
        try:
            count = await _delete_range_exact(event.chat_id, marker["target_id"], replied.id, [marker["control_id"], event.id])
        except ValueError:
            RANGE_STARTS.pop(event.chat_id, None)
            await event.edit("❌ فشلت العملية يجب أن تكون النهاية بعد البداية")
            return
        except PermissionError:
            RANGE_STARTS.pop(event.chat_id, None)
            await event.edit("❌ تعذر المسح ليس لديك صلاحية حذف رسائل الاخرين")
            return
        except Exception:
            RANGE_STARTS.pop(event.chat_id, None)
            await event.edit("❌ تعذر المسح حدث خطأ أثناء حذف الرسائل")
            return
        RANGE_STARTS.pop(event.chat_id, None)
        await active_client().send_message(event.chat_id, f"✅ تم مسح {count} رسالة")
        return

    if lower in {"تحديث", "/تحديث", "reload", "/reload"}:
        try:
            result = await refresh_special()
            await event.edit("✅ تم تحديث البوت بنجاح")
            add_log("operation_log", "runtime_refresh", json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            await event.edit(f"❌ تعذر تحديث البوت: {type(exc).__name__}")
        return

    if lower in {"مهم", "حفظ مهم", "/مهم", "/حفظ_مهم"}:
        if not event.is_private or not event.is_reply:
            await event.edit("❌ فشلت العملية يجب استخدام الرد في الخاص لحفظ الرسالة كمهمة")
            return
        replied = await event.get_reply_message()
        sender = await replied.get_sender() if replied else None
        if not replied or not sender:
            await event.edit("❌ تعذر تحديد الرسالة")
            return
        local_id, _ = insert_message_once(replied.id, sender.id, event.chat_id, "incoming" if not replied.out else "outgoing", replied.raw_text, media_type(replied), None, str(replied.date))
        mark_important(local_id)
        await event.edit("⭐ تم حفظ الرسالة كمهمة بنجاح")
        return

    if lower in {"تقليد", "/تقليد"}:
        target2 = await _resolve_target(event)
        if not target2:
            await event.edit("❌ فشلت العملية يجب الرد على المستخدم أو كتابة منشنه")
            return
        existing = _load_profile_backup()
        if existing and existing.get("active"):
            await event.edit("ℹ️ التقليد مفعّل بالفعل ألغِ التقليد أولًا")
            return
        try:
            await mimic_user(target2)
            await event.edit("✅ تم تقليد المستخدم أو القروب أو القناة وتحديث البيانات والصورة بأحدث نسخة")
        except Exception as exc:
            await event.edit(f"❌ تعذر التقليد: {type(exc).__name__}")
        return

    if lower in {"الغاء التقليد", "إلغاء التقليد", "/الغاء التقليد", "/إلغاء التقليد"}:
        try:
            await event.edit("✅ تم إلغاء التقليد واستعادة الحساب" if await restore_profile() else "ℹ️ ما فيه تقليد مفعّل حاليًا")
        except Exception as exc:
            await event.edit(f"❌ تعذر إلغاء التقليد: {type(exc).__name__}")
        return

    if lower in {".كتم", "كتم", "/كتم", ".mute", "mute"}:
        if not event.is_reply:
            await event.edit("⚠️ رد على رسالة المستخدم أولًا ثم أرسل أمر الكتم")
            return
        replied = await event.get_reply_message()
        target3 = await replied.get_sender() if replied else None
        if not target3:
            await event.edit("⚠️ لم أستطع تحديد صاحب الرسالة")
            return
        if not event.is_private:
            try:
                entity = await active_client().get_entity(event.chat_id)
                me = await active_client().get_me()
                perms = await active_client().get_permissions(entity, me)
                if not getattr(perms, "is_creator", False) and not getattr(perms, "delete_messages", False):
                    await event.edit("❌ تعذر المسح ليس لديك صلاحية حذف رسائل الاخرين")
                    return
            except Exception:
                await event.edit("❌ تعذر المسح ليس لديك صلاحية حذف رسائل الاخرين")
                return
        mute_in_chat(event.chat_id, target3.id, getattr(target3, "username", None), getattr(target3, "first_name", None) or getattr(target3, "last_name", None))
        await event.edit("🔇 تم كتم هذا الشخص")
        return

    if lower.startswith((".فك", "فك", "/فك", ".unmute", "unmute", "الغاء الكتم", "إلغاء الكتم", "/الغاء الكتم", "/إلغاء الكتم")):
        # Reply is the strongest/most reliable target selector. Always resolve
        # the replied message first, especially in groups and channels.
        target4 = None
        target4_id = None
        has_reply = bool(
            event.is_reply
            or getattr(event, "reply_to_msg_id", None) is not None
            or getattr(event, "reply_to", None) is not None
        )

        if has_reply:
            target4, target4_id = await _resolve_reply_user(event)
            if target4_id is None:
                await event.edit("⚠️ لم أستطع تحديد صاحب الرسالة للرد المرسل")
                return
        else:
            parts = text.split(maxsplit=1)
            argument = parts[1].strip() if len(parts) > 1 else ""
            if not argument:
                await event.edit("⚠️ رد على رسالة الشخص المكتوم أولًا أو اكتب الـ ID أو المنشن")
                return

            try:
                if argument.lstrip("-").isdigit():
                    target4 = await active_client().get_entity(int(argument))
                else:
                    target4 = await active_client().get_entity(argument.lstrip("@"))
            except Exception:
                target4 = None

            if not target4 and not event.is_private:
                row4 = get_chat_muted_user_by_username(event.chat_id, argument)
                if row4:
                    target4 = type("ReplyTarget", (), {"id": int(row4["user_id"])})()

            if not target4:
                await event.edit("⚠️ لم أستطع تحديد المستخدم من الـ ID أو المنشن")
                return
            target4_id = int(target4.id)

        if target4_id is None:
            target4_id = int(target4.id)

        if event.is_private:
            ok = unmute_user(target4_id)
        else:
            ok = unmute_in_chat(int(event.chat_id), target4_id)
        await event.edit("🔊 تم الغاء الكتم عن هذا المستخدم" if ok else "ℹ️ المستخدم غير موجود في قائمة المكتومين")
        return


async def runtime_watchdog():
    audit_tick = 0
    while True:
        await asyncio.sleep(30)
        try:
            if not active_client().is_connected():
                async with WATCHDOG_LOCK:
                    await active_client().connect()
                    add_log("operation_log", "telethon_reconnect", "تمت إعادة الاتصال تلقائيًا")
            audit_tick += 1
            if audit_tick >= 2:
                audit_tick = 0
                await audit_recent_private_deletions()
        except Exception as exc:
            add_log("operation_log", "watchdog_error", f"{type(exc).__name__}: {exc}")


def session_path_for_bot_user(bot_user_id):
    root = ROOT / "storage" / "sessions" / str(int(bot_user_id))
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "special_user")


async def get_or_create_user_client(bot_user_id):
    bot_user_id = int(bot_user_id)
    if ADMIN_ID and str(bot_user_id) == str(ADMIN_ID):
        set_active_client(client, bot_user_id)
        return client
    existing = USER_CLIENTS.get(bot_user_id)
    if existing:
        set_active_client(existing, bot_user_id)
        return existing
    row = get_user_session(bot_user_id)
    session_path = row["session_path"] if row and row["session_path"] else session_path_for_bot_user(bot_user_id)
    uc = TelegramClient(session_path, int(API_ID), API_HASH)
    USER_CLIENTS[bot_user_id] = uc
    CLIENT_BOT_IDS[id(uc)] = bot_user_id
    set_active_client(uc, bot_user_id)
    return uc


async def is_user_logged_in(bot_user_id):
    bot_user_id = int(bot_user_id)
    # The developer/owner is authenticated by the dedicated terminal-launched
    # session (`special_user`). It must never be asked to log in through the bot.
    if ADMIN_ID and str(bot_user_id) == str(ADMIN_ID):
        try:
            if not client.is_connected():
                await client.connect()
            return bool(await client.is_user_authorized())
        except Exception:
            return False
    uc = await get_or_create_user_client(bot_user_id)
    if not uc.is_connected():
        await uc.connect()
    return bool(await uc.is_user_authorized())


async def disconnect_user_client(bot_user_id, delete_session=False):
    bot_user_id = int(bot_user_id)
    uc = USER_CLIENTS.pop(bot_user_id, None)
    CLIENT_BOT_IDS.pop(id(uc), None) if uc else None
    if uc and uc.is_connected():
        await uc.disconnect()
    if delete_session:
        row = get_user_session(bot_user_id)
        delete_user_session(bot_user_id)
        if row:
            try:
                for suffix in ("", ".session", ".session-journal"):
                    Path(str(row["session_path"]) + suffix).unlink(missing_ok=True)
            except Exception:
                pass


async def start_authorized_user_client(bot_user_id):
    bot_user_id = int(bot_user_id)
    # Owner uses the already-authenticated terminal session, not a bot login flow.
    if ADMIN_ID and str(bot_user_id) == str(ADMIN_ID):
        if not client.is_connected():
            await client.connect()
        if not await client.is_user_authorized():
            return False
        set_active_client(client, bot_user_id)
        return True
    uc = await get_or_create_user_client(bot_user_id)
    if not uc.is_connected():
        await uc.connect()
    if not await uc.is_user_authorized():
        return False
    me = await uc.get_me()
    save_user_session(bot_user_id, session_path_for_bot_user(bot_user_id), int(me.id), None, "active")
    # Bind the same automation handlers to this independent account.
    if not getattr(uc, "_special_handlers_bound", False):
        uc.add_event_handler(incoming, events.NewMessage(incoming=True))
        uc.add_event_handler(incoming_edit, events.MessageEdited(incoming=True))
        uc.add_event_handler(deleted_event, events.MessageDeleted)
        uc.add_event_handler(outgoing, events.NewMessage(outgoing=True))
        uc._special_handlers_bound = True
    return True


async def start_all_authorized_users():
    for row in list_user_sessions():
        bot_uid = int(row["bot_user_id"])
        allowed = get_allowed_user(bot_uid)
        if not allowed or allowed["status"] != "active":
            continue
        try:
            ok = await start_authorized_user_client(bot_uid)
            if ok:
                print(f"🟢 User session restored: bot_user={bot_uid}")
        except Exception as exc:
            add_log("operation_log", "user_session_restore_failed", f"bot_user={bot_uid}:{type(exc).__name__}")


async def start_user_client():
    init_database()
    last_error = None
    for attempt in range(1, 6):
        try:
            await active_client().start()
            break
        except Exception as exc:
            last_error = exc
            if "database is locked" not in str(exc).lower():
                raise
            print(f"⚠️ جلسة Telethon مقفولة — المحاولة {attempt}/5")
            await asyncio.sleep(2)
    else:
        print(f"❌ تعذر تشغيل Telethon: {type(last_error).__name__}: {last_error}")
        return
    me = await active_client().get_me()
    set_active_client(client, int(ADMIN_ID) if ADMIN_ID else None)
    print("🟢 Special User Automation يعمل")
    print(f"الحساب: {me.first_name}")
    print(f"ID: {me.id}")
    asyncio.create_task(runtime_watchdog())
    await active_client().run_until_disconnected()


async def resolve_username(value):
    value = str(value).strip().lstrip("@")
    entity = await active_client().get_entity(value)
    if not hasattr(entity, "id") or getattr(entity, "bot", False) or getattr(entity, "deleted", False):
        return None
    if not isinstance(entity, types.User):
        return None
    return int(entity.id)
