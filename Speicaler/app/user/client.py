import asyncio
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telethon import TelegramClient, events, functions

from app.core.config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from app.core.database import *
from app.core.ai import ask_gemini
from app.user.moderation import check_muted, mute_in_chat, unmute_in_chat, is_muted_in_chat


client = TelegramClient("special_user", int(API_ID), API_HASH)
bot = Bot(token=BOT_TOKEN)

ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROOT = ROOT / "storage" / "media"
PROFILE_ROOT = ROOT / "storage" / "profile_mimic"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
PROFILE_BACKUP = PROFILE_ROOT / "backup.json"

RANGE_STARTS: dict[int, dict[str, int]] = {}
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
    if message.voice or message.audio:
        return "audio"
    return "file"


def has_link(text):
    return bool(text and re.search(r"https?://|t\.me/", text, re.I))


def is_ai_request(text):
    if not text:
        return False, ""
    m = re.match(r"^\s*سبيشل(?:\s*[:،,-]?\s*)(.*)$", text, re.I | re.S)
    if not m:
        return False, ""
    return True, m.group(1).strip()


async def archive_media(event, user_id, direction):
    if not event.message or not event.message.media:
        return None
    folder = MEDIA_ROOT / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return await event.download_media(file=str(folder / f"{direction}_{event.id}"))
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
    caption = (
        "📥 تم حفظ وسائط من الخاص\n\n"
        f"👤 الاسم: {name}\n"
        f"🆔 ID: {sender.id}\n"
        f"🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n"
        f"🕐 التاريخ: {replied.date}"
    )
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
    return (
        (getattr(user, "first_name", None) or "").strip(),
        (getattr(user, "last_name", None) or "").strip(),
    )


def _load_profile_backup():
    if not PROFILE_BACKUP.exists():
        return None
    try:
        return json.loads(PROFILE_BACKUP.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_profile_backup(data):
    PROFILE_BACKUP.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def _delete_current_profile_photos():
    try:
        me = await client.get_me()
        photos = await client.get_profile_photos(me, limit=100)
        if photos:
            await client(functions.photos.DeletePhotosRequest(id=list(photos)))
    except Exception as exc:
        add_log("operation_log", "profile_photo_delete_failed", type(exc).__name__)


async def _backup_current_profile():
    existing = _load_profile_backup()
    if existing and existing.get("active"):
        return existing
    me = await client.get_me()
    first, last = _profile_name(me)
    backup = {
        "active": True,
        "first_name": first,
        "last_name": last,
        "about": getattr(me, "about", None) or "",
        "photo": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    photos = await client.get_profile_photos(me, limit=1)
    if photos:
        photo_path = PROFILE_ROOT / "original_profile_photo"
        downloaded = await client.download_media(photos[0], file=str(photo_path))
        if downloaded:
            backup["photo"] = str(downloaded)
    _save_profile_backup(backup)
    return backup


async def _resolve_target(event):
    if event.is_reply:
        reply = await event.get_reply_message()
        if reply:
            sender = await reply.get_sender()
            if sender:
                return sender
    match = re.search(r"@([A-Za-z0-9_]{3,32})", event.raw_text or "")
    if match:
        try:
            return await client.get_entity(match.group(1))
        except Exception:
            return None
    return None


async def _apply_mimic_target(target):
    first, last = _profile_name(target)
    about = getattr(target, "about", None) or ""
    await client(functions.account.UpdateProfileRequest(first_name=first or "Special", last_name=last, about=about))
    # Fetch fresh entity/profile photo every time; avoid cached dialog data.
    refreshed = await client.get_entity(target.id)
    photos = await client.get_profile_photos(refreshed, limit=1)
    await _delete_current_profile_photos()
    if photos:
        temp_dir = Path(tempfile.mkdtemp(prefix="special_mimic_"))
        try:
            path = await client.download_media(photos[0], file=str(temp_dir / "latest_profile"))
            if path:
                uploaded = await client.upload_file(path)
                await client(functions.photos.UploadProfilePhotoRequest(file=uploaded))
        finally:
            for item in temp_dir.iterdir():
                if item.is_file():
                    item.unlink(missing_ok=True)
            temp_dir.rmdir()


async def mimic_user(target):
    backup = await _backup_current_profile()
    backup.update({
        "mimic_target_id": int(target.id),
        "mimic_target_username": getattr(target, "username", None),
        "active": True,
    })
    _save_profile_backup(backup)
    await _apply_mimic_target(target)
    add_log("operation_log", "profile_mimic_started", f"target={target.id}")


async def refresh_mimic_profile():
    backup = _load_profile_backup()
    if not backup or not backup.get("active") or not backup.get("mimic_target_id"):
        return False
    target = await client.get_entity(int(backup["mimic_target_id"]))
    await _apply_mimic_target(target)
    backup["mimic_target_username"] = getattr(target, "username", None)
    backup["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    _save_profile_backup(backup)
    return True


async def restore_profile():
    backup = _load_profile_backup()
    if not backup or not backup.get("active"):
        return False
    await client(functions.account.UpdateProfileRequest(
        first_name=backup.get("first_name") or "Special",
        last_name=backup.get("last_name") or "",
        about=backup.get("about") or "",
    ))
    await _delete_current_profile_photos()
    if backup.get("photo") and Path(backup["photo"]).exists():
        uploaded = await client.upload_file(backup["photo"])
        await client(functions.photos.UploadProfilePhotoRequest(file=uploaded))
    backup["active"] = False
    _save_profile_backup(backup)
    return True


async def sync_all_private_users():
    """Discover every real human in private dialogs and add them to Special."""
    added = updated = skipped = 0
    me = await client.get_me()
    async for dialog in client.iter_dialogs():
        if not dialog.is_user:
            continue
        user = dialog.entity
        if user.id == me.id or getattr(user, "bot", False) or getattr(user, "deleted", False):
            skipped += 1
            continue
        name = getattr(user, "first_name", None) or getattr(user, "last_name", None) or "مستخدم"
        exists = get_private_chat(user.id)
        upsert_private_chat(user.id, getattr(user, "username", None), name, is_bot=False, is_deleted_user=False)
        if exists:
            updated += 1
        else:
            added += 1
    add_log("operation_log", "sync_private_users", f"added={added},updated={updated},skipped={skipped}")
    return {"added": added, "updated": updated, "skipped": skipped}


async def import_all_private_history():
    """Import all human private history once, preserving repeated real messages exactly once each."""
    async with IMPORT_LOCK:
        users = await sync_all_private_users()
        chats = messages = skipped = 0
        me = await client.get_me()
        async for dialog in client.iter_dialogs():
            if not dialog.is_user:
                continue
            entity = dialog.entity
            if entity.id == me.id or getattr(entity, "bot", False) or getattr(entity, "deleted", False):
                continue
            chats += 1
            name = getattr(entity, "first_name", None) or getattr(entity, "last_name", None) or "مستخدم"
            upsert_private_chat(entity.id, getattr(entity, "username", None), name, is_bot=False, is_deleted_user=False)
            async for msg in client.iter_messages(entity, reverse=True):
                direction = "outgoing" if getattr(msg, "out", False) else "incoming"
                inserted_id, inserted = insert_message_once(
                    msg.id, entity.id, entity.id, direction,
                    msg.raw_text, media_type(msg), None, str(msg.date)
                )
                if inserted:
                    increment_stats(entity.id, media_type(msg), has_link(msg.raw_text))
                    messages += 1
                else:
                    skipped += 1
        dedupe_messages()
        add_log("operation_log", "private_history_import", f"chats={chats},new={messages},skipped={skipped}")
        return {"chats": chats, "messages": messages, "skipped": skipped, **users}


async def _send_edit_notification(sender, old_text, new_text, message_id):
    if not ADMIN_ID or get_setting("notify_edited", "1") != "1":
        return
    name = getattr(sender, "first_name", None) or getattr(sender, "last_name", None) or "مستخدم"
    username = getattr(sender, "username", None)
    url = f"https://t.me/{username}" if username else f"tg://user?id={sender.id}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 فتح حساب الشخص", url=url)]])
    body = (
        "✏️ تم تعديل رسالة في الخاص\n\n"
        f"👤 الاسم: {name}\n"
        f"🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n"
        f"🆔 ID: {sender.id}\n"
        f"🧾 Message ID: {message_id}\n\n"
        f"قبل:\n{old_text or '[بدون نص]'}\n\n"
        f"بعد:\n{new_text or '[بدون نص]'}"
    )
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
    body = (
        "🗑️ تم حذف رسالة من الخاص\n\n"
        f"👤 الاسم: {row['display_name'] or 'مستخدم'}\n"
        f"🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n"
        f"🆔 ID: {row['user_id']}\n\n"
        f"💬 {row['text'] or '[' + (row['media_type'] or 'وسائط') + ']'}"
    )
    try:
        await bot.send_message(int(ADMIN_ID), body[:3900], reply_markup=markup)
    except Exception:
        pass


async def _delete_range_exact(chat_id, start_id, end_id, control_ids):
    if end_id < start_id:
        raise ValueError("invalid_range")
    if chat_id not in {None, 0} and not (get_private_chat(chat_id) and not isinstance(chat_id, bool)):
        pass
    entity = await client.get_entity(chat_id)
    if not getattr(entity, "megagroup", False) and not getattr(entity, "broadcast", False):
        # private chats can delete normally
        pass
    if not entity.__class__.__name__ == "User":
        me = await client.get_me()
        try:
            perms = await client.get_permissions(entity, me)
            if not getattr(perms, "is_creator", False) and not getattr(perms, "delete_messages", False):
                raise PermissionError("delete_messages")
        except PermissionError:
            raise
        except Exception:
            raise PermissionError("delete_messages")
    ids = set(range(start_id, end_id + 1))
    ids.update(int(x) for x in control_ids if x)
    ordered = sorted(ids)
    deleted = 0
    for offset in range(0, len(ordered), 100):
        batch = ordered[offset:offset + 100]
        try:
            result = await client.delete_messages(chat_id, batch)
            deleted += len(result or [])
        except Exception:
            for mid in batch:
                try:
                    result = await client.delete_messages(chat_id, [mid])
                    if result:
                        deleted += 1
                except Exception:
                    pass
    return deleted


async def refresh_special():
    init_database()
    dedupe_messages()
    await sync_all_private_users()
    refreshed = await refresh_mimic_profile()
    if not client.is_connected():
        await client.connect()
    return {"mimic_refreshed": refreshed, "connected": client.is_connected()}


@client.on(events.NewMessage(incoming=True))
async def incoming(event):
    sender = await event.get_sender()
    if not sender:
        return

    # AI request takes precedence after basic identity capture.
    ai_ok, ai_prompt = is_ai_request(event.raw_text)
    if ai_ok and ai_prompt:
        try:
            answer = await ask_gemini(ai_prompt)
            if answer:
                await event.reply(answer[:4000])
        except Exception as exc:
            add_log("operation_log", "gemini_failed", f"{type(exc).__name__}: {exc}")
        return

    if event.is_private:
        if getattr(sender, "bot", False):
            return
        name = getattr(sender, "first_name", None) or getattr(sender, "last_name", None) or "مستخدم"
        was_known = get_private_chat(sender.id) is not None
        upsert_private_chat(sender.id, getattr(sender, "username", None), name, is_bot=False, is_deleted_user=getattr(sender, "deleted", False))
        if not was_known and get_setting("notify_new_contact", "1") == "1" and ADMIN_ID:
            username = getattr(sender, "username", None)
            url = f"https://t.me/{username}" if username else f"tg://user?id={sender.id}"
            markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 فتح المستخدم", url=url)]])
            try:
                await bot.send_message(int(ADMIN_ID), f"👤 شخص جديد في الخاص\n\nالاسم: {name}\nID: {sender.id}\nUsername: {('@' + username) if username else 'لا يوجد يوزر'}", reply_markup=markup)
            except Exception:
                pass
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

    if is_muted_in_chat(event.chat_id, sender.id):
        try:
            await event.delete()
        except Exception:
            add_log("operation_log", "group_mute_delete_failed", f"chat={event.chat_id},user={sender.id}")


@client.on(events.MessageEdited(incoming=True))
async def incoming_edit(event):
    if not event.is_private:
        return
    sender = await event.get_sender()
    if not sender:
        return
    row = get_message_record(event.id, event.chat_id, "incoming")
    old_text = row["text"] if row else ""
    if row:
        record_edit(event.id, event.chat_id, sender.id, "incoming", old_text, event.raw_text)
    else:
        insert_message_once(event.id, sender.id, event.chat_id, "incoming", event.raw_text, media_type(event.message), None, str(event.date))
        record_edit(event.id, event.chat_id, sender.id, "incoming", "", event.raw_text)
    await _send_edit_notification(sender, old_text, event.raw_text, event.id)


@client.on(events.MessageDeleted)
async def deleted_event(event):
    ids = list(getattr(event, "deleted_ids", []) or [])
    chat_id = getattr(event, "chat_id", None)
    rows = get_messages_by_telegram_ids(ids, chat_id=chat_id) if chat_id else []
    if not rows:
        for mid in ids:
            candidates = get_private_records_by_message_id(mid)
            # Private deletions don't carry chat ID. Notify only stored private matches.
            rows.extend(candidates)
    seen = set()
    for row in rows:
        key = row["id"]
        if key in seen:
            continue
        seen.add(key)
        mark_message_deleted(row["telegram_message_id"], row["chat_id"], row["direction"])
        await _send_delete_notification(row)


@client.on(events.NewMessage(outgoing=True))
async def outgoing(event):
    ai_ok, ai_prompt = is_ai_request(event.raw_text)
    if ai_ok and ai_prompt:
        try:
            answer = await ask_gemini(ai_prompt)
            if answer:
                await event.reply(answer[:4000])
        except Exception as exc:
            add_log("operation_log", "gemini_failed", f"{type(exc).__name__}: {exc}")
        return

    target = await event.get_chat()
    text = (event.raw_text or "").strip()
    lower = text.lower()

    # AI / control commands are only processed when they are explicit; normal messages are stored.
    if event.is_private:
        name = getattr(target, "first_name", None) or getattr(target, "last_name", None) or "مستخدم"
        upsert_private_chat(target.id, getattr(target, "username", None), name)
        media_path = await archive_media(event, target.id, "out") if event.message and event.message.media else None
        inserted_id, inserted = insert_message_once(
            event.id, target.id, event.chat_id, "outgoing", event.raw_text, media_type(event.message), media_path, str(event.date)
        )
        if inserted:
            increment_stats(target.id, media_type(event.message), has_link(event.raw_text))
        if event.is_reply:
            replied = await event.get_reply_message()
            if replied and replied.media:
                await save_replied_media(event, replied, target)

    if lower in {"/بداية", "بداية"}:
        if not event.is_reply:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        replied = await event.get_reply_message()
        if not replied:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        RANGE_STARTS[event.chat_id] = {"target_id": replied.id, "control_id": event.id}
        await event.edit("✅ تم تحديد البداية بنجاح")
        return

    if lower in {"/نهاية", "نهاية"}:
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
        await client.send_message(event.chat_id, f"✅ تم حذف {count} رسالة")
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
        if not event.is_private:
            await event.edit("❌ حفظ المهم متاح حاليًا في الخاص فقط")
            return
        if not event.is_reply:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة لحفظها كمهمة")
            return
        replied = await event.get_reply_message()
        if not replied:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة لحفظها كمهمة")
            return
        sender = await replied.get_sender()
        uid = getattr(sender, "id", None) or event.chat_id
        local_id, _ = insert_message_once(replied.id, uid, event.chat_id, "incoming" if not replied.out else "outgoing", replied.raw_text, media_type(replied), None, str(replied.date))
        if local_id:
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
            await event.edit("✅ تم تقليد المستخدم وتحديث بياناته وصورته بأحدث نسخة")
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
                entity = await client.get_entity(event.chat_id)
                me = await client.get_me()
                perms = await client.get_permissions(entity, me)
                if not getattr(perms, "is_creator", False) and not getattr(perms, "delete_messages", False):
                    await event.edit("❌ تعذر المسح ليس لديك صلاحية حذف رسائل الاخرين")
                    return
            except Exception:
                await event.edit("❌ تعذر المسح ليس لديك صلاحية حذف رسائل الاخرين")
                return
        mute_in_chat(event.chat_id, target3.id, getattr(target3, "username", None), getattr(target3, "first_name", None) or getattr(target3, "last_name", None))
        await event.edit("🔇 تم كتم هذا الشخص")
        return

    if lower in {".فك", "فك", "/فك", ".unmute", "unmute", "الغاء الكتم", "إلغاء الكتم", "/الغاء الكتم", "/إلغاء الكتم"}:
        if not event.is_reply:
            await event.edit("⚠️ رد على رسالة المستخدم أولًا ثم أرسل أمر إلغاء الكتم")
            return
        replied = await event.get_reply_message()
        target4 = await replied.get_sender() if replied else None
        if not target4:
            await event.edit("⚠️ لم أستطع تحديد صاحب الرسالة")
            return
        await event.edit("🔊 تم الغاء الكتم عن هذا المستخدم" if unmute_in_chat(event.chat_id, target4.id) else "ℹ️ المستخدم غير موجود في قائمة المكتومين")
        return


async def runtime_watchdog():
    while True:
        await asyncio.sleep(45)
        try:
            if not client.is_connected():
                async with WATCHDOG_LOCK:
                    await client.connect()
                    add_log("operation_log", "telethon_reconnect", "تمت إعادة الاتصال تلقائيًا")
        except Exception as exc:
            add_log("operation_log", "watchdog_error", f"{type(exc).__name__}: {exc}")


async def start_user_client():
    init_database()
    last_error = None
    for attempt in range(1, 6):
        try:
            await client.start()
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
    me = await client.get_me()
    print("🟢 Special User Automation يعمل")
    print(f"الحساب: {me.first_name}")
    print(f"ID: {me.id}")
    asyncio.create_task(runtime_watchdog())
    await client.run_until_disconnected()


async def resolve_username(value):
    value = str(value).strip().lstrip("@")
    entity = await client.get_entity(value)
    if getattr(entity, "bot", False) or getattr(entity, "deleted", False) or not hasattr(entity, "id"):
        return None
    # Only real human accounts are accepted for broadcast exclusions.
    if entity.__class__.__name__ != "User":
        return None
    return int(entity.id)
