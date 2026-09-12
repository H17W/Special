import asyncio
import json
import os
import re
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telethon import TelegramClient, events, functions, types

from app.core.config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from app.core.database import *
from app.core.ai import ask_gemini, parse_request
from app.user.moderation import check_muted, mute_in_chat, unmute_in_chat, is_muted_in_chat

from app.core.database import account_scope, get_account_id, init_account_database

# Bot API instance is injected by app.main at startup.
bot = None

def set_bot_instance(instance):
    global bot
    bot = instance


class MultiClientManager:
    def __init__(self):
        self.clients = {}
        self.handlers = []
        self.login_clients = {}
        self.login_meta = {}

    def register_handler(self, event_builder, func):
        self.handlers.append((event_builder, func))
        for account_id, client in list(self.clients.items()):
            self._attach(client, account_id, event_builder, func)

    def _attach(self, client, account_id, event_builder, func):
        async def wrapped(event):
            with account_scope(account_id):
                return await func(event)
        client.add_event_handler(wrapped, event_builder)

    async def add_account(self, account_id, start=True):
        account_id = str(account_id)
        if account_id in self.clients:
            return self.clients[account_id]
        root = Path(__file__).resolve().parents[2] / 'storage' / 'accounts' / account_id
        session_path = root / 'session' / 'telegram.session'
        session_path.parent.mkdir(parents=True, exist_ok=True)
        init_account_database(account_id)
        c = TelegramClient(str(session_path), int(API_ID), API_HASH)
        await c.connect()
        if not await c.is_user_authorized():
            await c.disconnect()
            return None
        self.clients[account_id] = c
        for event_builder, func in self.handlers:
            self._attach(c, account_id, event_builder, func)
        if start:
            asyncio.create_task(c.run_until_disconnected())
            asyncio.create_task(self._watchdog(account_id))
        return c

    async def begin_login(self, account_id, phone):
        account_id = str(account_id)
        if account_id in self.login_clients:
            try: await self.login_clients[account_id].disconnect()
            except Exception: pass
        root = Path(__file__).resolve().parents[2] / 'storage' / 'accounts' / account_id
        session_path = root / 'session' / 'telegram.session'
        session_path.parent.mkdir(parents=True, exist_ok=True)
        init_account_database(account_id)
        c = TelegramClient(str(session_path), int(API_ID), API_HASH)
        await c.connect()
        sent = await c.send_code_request(phone)
        self.login_clients[account_id] = c
        self.login_meta[account_id] = {'phone': phone, 'phone_code_hash': sent.phone_code_hash}
        return sent

    async def finish_code(self, account_id, code):
        account_id = str(account_id)
        c = self.login_clients.get(account_id)
        meta = self.login_meta.get(account_id)
        if not c or not meta:
            raise RuntimeError('جلسة تسجيل الدخول منتهية')
        try:
            await c.sign_in(phone=meta['phone'], code=code, phone_code_hash=meta['phone_code_hash'])
        except Exception as exc:
            from telethon.errors import SessionPasswordNeededError
            if isinstance(exc, SessionPasswordNeededError):
                return '2fa'
            raise
        await self._finalize_login(account_id)
        return 'done'

    async def finish_password(self, account_id, password):
        c = self.login_clients.get(str(account_id))
        if not c:
            raise RuntimeError('جلسة تسجيل الدخول منتهية')
        await c.sign_in(password=password)
        await self._finalize_login(str(account_id))
        return 'done'

    async def _finalize_login(self, account_id):
        c = self.login_clients.pop(str(account_id), None)
        self.login_meta.pop(str(account_id), None)
        if not c:
            return
        self.clients[str(account_id)] = c
        for event_builder, func in self.handlers:
            self._attach(c, str(account_id), event_builder, func)
        asyncio.create_task(c.run_until_disconnected())
        asyncio.create_task(self._watchdog(str(account_id)))

    async def _watchdog(self, account_id):
        with account_scope(str(account_id)):
            await runtime_watchdog()

    async def logout(self, account_id):
        account_id = str(account_id)
        c = self.clients.pop(account_id, None)
        if c:
            try: await c.log_out()
            finally:
                try: await c.disconnect()
                except Exception: pass
        return True

    def get(self, account_id=None):
        return self.clients.get(str(account_id or get_account_id()))

    def status(self, account_id):
        c = self.clients.get(str(account_id))
        return bool(c and c.is_connected())


manager = MultiClientManager()


class ClientProxy:
    def __getattr__(self, name):
        if name == 'on':
            return self.on
        client = manager.get()
        if client is None:
            raise RuntimeError('لا توجد جلسة Telegram مفعلة لهذا الحساب')
        return getattr(client, name)

    def on(self, event_builder):
        def decorator(func):
            manager.register_handler(event_builder, func)
            return func
        return decorator


client = ClientProxy()

# Current-account paths are derived inside helpers, never shared between users.
def account_root(account_id=None):
    aid = str(account_id or get_account_id())
    return Path(__file__).resolve().parents[2] / 'storage' / 'accounts' / aid


def account_media_root(account_id=None):
    p = account_root(account_id) / 'media'; p.mkdir(parents=True, exist_ok=True); return p

def account_profile_root(account_id=None):
    p = account_root(account_id) / 'profile_mimic'; p.mkdir(parents=True, exist_ok=True); return p


BOT_OWNER_TARGET = lambda: int(get_account_id()) if str(get_account_id()).isdigit() else None

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
    if message.voice or message.audio:
        return "audio"
    return "file"


def has_link(text):
    return bool(text and re.search(r"https?://|t\.me/", text, re.I))


async def archive_media(event, user_id, direction):
    """Send media directly to the bot private chat, then delete the temporary file.
    The database stores the message metadata only; media bytes are not kept on disk.
    """
    if not event.message or not event.message.media:
        return None
    target_id = int(get_account_id()) if str(get_account_id()).isdigit() else None
    if not target_id or bot is None:
        return None
    sender = None
    try:
        sender = await event.get_sender()
    except Exception:
        pass
    name = (getattr(sender, 'first_name', None) or getattr(sender, 'last_name', None) or 'مستخدم') if sender else 'مستخدم'
    username = getattr(sender, 'username', None) if sender else None
    if direction == 'out':
        try:
            chat = await event.get_chat()
            name = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or getattr(chat, 'last_name', None) or name
            username = getattr(chat, 'username', None) or username
        except Exception:
            pass
    url = f"https://t.me/{username}" if username else (f"tg://user?id={user_id}" if str(user_id).isdigit() else None)
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='👤 فتح المستخدم', url=url)]]) if url else None
    caption = (f"📥 وسائط محفوظة من {'الخاص' if event.is_private else 'المحادثة'}\n\n"
               f"👤 الاسم: {name}\n🆔 ID: {user_id}\n"
               f"🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n"
               f"📌 النوع: {media_type(event.message) or 'media'}\n🕐 التاريخ: {event.date}")[:1000]
    temp_dir = Path(tempfile.mkdtemp(prefix='special_media_'))
    try:
        path = await event.download_media(file=str(temp_dir / f'media_{event.id}'))
        if not path:
            return None
        f = FSInputFile(path)
        mt = media_type(event.message)
        if event.message.photo:
            await bot.send_photo(target_id, f, caption=caption, reply_markup=markup)
        elif event.message.video:
            await bot.send_video(target_id, f, caption=caption, reply_markup=markup)
        elif event.message.voice:
            await bot.send_voice(target_id, f, caption=caption, reply_markup=markup)
        elif event.message.audio:
            await bot.send_audio(target_id, f, caption=caption, reply_markup=markup)
        elif event.message.sticker:
            await bot.send_document(target_id, f, caption=caption, reply_markup=markup)
        elif event.message.gif:
            await bot.send_animation(target_id, f, caption=caption, reply_markup=markup)
        else:
            await bot.send_document(target_id, f, caption=caption, reply_markup=markup)
        return None
    except Exception as exc:
        add_log('operation_log', 'media_archive_failed', f'{type(exc).__name__}: {exc}')
        return None
    finally:
        try:
            for item in temp_dir.iterdir():
                if item.is_file(): item.unlink(missing_ok=True)
            temp_dir.rmdir()
        except Exception:
            pass


async def send_text_chunks(text):
    target_id = int(get_account_id()) if str(get_account_id()).isdigit() else None
    if not target_id or bot is None:
        return
    for i in range(0, len(text or ""), 4000):
        await bot.send_message(target_id, text[i:i + 4000])


async def save_replied_media(event, replied, sender):
    target_id = int(get_account_id()) if str(get_account_id()).isdigit() else None
    if not replied or not replied.media or not target_id or bot is None:
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
            await bot.send_photo(target_id, f, caption=caption, reply_markup=markup)
        elif replied.video:
            await bot.send_video(target_id, f, caption=caption, reply_markup=markup)
        elif replied.voice:
            await bot.send_voice(target_id, f, caption=caption, reply_markup=markup)
        elif replied.audio:
            await bot.send_audio(target_id, f, caption=caption, reply_markup=markup)
        else:
            await bot.send_document(target_id, f, caption=caption, reply_markup=markup)
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
    if not (account_profile_root() / "backup.json").exists():
        return None
    try:
        return json.loads((account_profile_root() / "backup.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_profile_backup(data):
    (account_profile_root() / "backup.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    backup = {"active": True, "first_name": first, "last_name": last, "username": getattr(me, "username", None), "about": getattr(me, "about", None) or "", "photo": None, "created_at": datetime.now(timezone.utc).isoformat()}
    photos = await client.get_profile_photos(me, limit=1)
    if photos:
        photo_path = account_profile_root() / "original_profile_photo"
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


async def _fresh_about(target):
    try:
        if isinstance(target, types.User):
            full = await client(functions.users.GetFullUserRequest(target))
            return getattr(full.full_user, "about", None) or ""
        if isinstance(target, types.Channel):
            full = await client(functions.channels.GetFullChannelRequest(target))
            return getattr(full.full_chat, "about", None) or ""
        if isinstance(target, types.Chat):
            full = await client(functions.messages.GetFullChatRequest(target.id))
            return getattr(full.full_chat, "about", None) or ""
    except Exception:
        pass
    return getattr(target, "about", None) or ""


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
            checked = await client(functions.account.CheckUsernameRequest(username=candidate))
            if checked:
                return candidate
        except Exception:
            continue
    return None


async def _apply_mimic_target(target):
    refreshed = await client.get_entity(target.id)
    settings = {
        "mimic_enabled": get_setting("mimic_enabled", "1"),
        "mimic_name": get_setting("mimic_name", "1"),
        "mimic_photo": get_setting("mimic_photo", "1"),
        "mimic_bio": get_setting("mimic_bio", "1"),
        "mimic_username": get_setting("mimic_username", "0"),
        "mimic_location": get_setting("mimic_location", "0"),
    }
    if settings["mimic_enabled"] != "1":
        raise RuntimeError("التقليد معطل من إعدادات البوت")

    first, last = _profile_name(refreshed)
    about = await _fresh_about(refreshed) if settings["mimic_bio"] == "1" else None
    kwargs = {}
    if settings["mimic_name"] == "1":
        kwargs.update(first_name=first or "Special", last_name=last)
    if settings["mimic_bio"] == "1":
        kwargs["about"] = about
    if kwargs:
        await client(functions.account.UpdateProfileRequest(**kwargs))

    if settings["mimic_photo"] == "1":
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

    if settings["mimic_username"] == "1" and isinstance(refreshed, types.User) and getattr(refreshed, "username", None):
        candidate = await _available_similar_username(refreshed.username)
        if candidate:
            try:
                await client(functions.account.UpdateUsernameRequest(username=candidate))
            except Exception as exc:
                add_log("operation_log", "mimic_username_failed", f"{type(exc).__name__}: {exc}")

    if settings["mimic_location"] == "1":
        add_log("operation_log", "mimic_location_unavailable", "Telegram personal profile location is not exposed by UpdateProfile in the current Telethon API; skipped safely.")


async def mimic_user(target):
    if get_setting("mimic_enabled", "1") != "1":
        raise RuntimeError("التقليد معطل من إعدادات البوت")
    backup = await _backup_current_profile()
    backup.update({"mimic_target_id": int(target.id), "mimic_target_username": getattr(target, "username", None), "mimic_target_type": target.__class__.__name__, "active": True})
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
    await client(functions.account.UpdateProfileRequest(first_name=backup.get("first_name") or "Special", last_name=backup.get("last_name") or "", about=backup.get("about") or ""))
    original_username = backup.get("username")
    if original_username:
        try:
            await client(functions.account.UpdateUsernameRequest(username=original_username))
        except Exception as exc:
            add_log("operation_log", "restore_username_failed", f"{type(exc).__name__}: {exc}")
    await _delete_current_profile_photos()
    if backup.get("photo") and Path(backup["photo"]).exists():
        uploaded = await client.upload_file(backup["photo"])
        await client(functions.photos.UploadProfilePhotoRequest(file=uploaded))
    backup["active"] = False
    _save_profile_backup(backup)
    return True


async def sync_all_private_users():
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
                _, inserted = insert_message_once(msg.id, entity.id, entity.id, direction, msg.raw_text, media_type(msg), None, str(msg.date))
                if inserted:
                    increment_stats(entity.id, media_type(msg), has_link(msg.raw_text))
                    messages += 1
                else:
                    skipped += 1
        # Safety pass: physical message identity is chat+Telegram message ID. Repeated text is preserved if IDs differ.
        dedupe_messages()
        add_log("operation_log", "private_history_import", f"chats={chats},new={messages},skipped={skipped}")
        return {"chats": chats, "messages": messages, "skipped": skipped, **users}


async def _send_edit_notification(sender, old_text, new_text, message_id):
    if not str(get_account_id()).isdigit() or get_setting("notify_edited", "1") != "1":
        return
    if getattr(sender, "bot", False) or getattr(sender, "deleted", False):
        return
    name = getattr(sender, "first_name", None) or getattr(sender, "last_name", None) or "مستخدم"
    username = getattr(sender, "username", None)
    url = f"https://t.me/{username}" if username else f"tg://user?id={sender.id}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 فتح حساب الشخص", url=url)]])
    body = f"✏️ تم تعديل رسالة في الخاص\n\n👤 الاسم: {name}\n🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n🆔 ID: {sender.id}\n🧾 Message ID: {message_id}\n\nقبل:\n{old_text or '[بدون نص]'}\n\nبعد:\n{new_text or '[بدون نص]'}"
    try:
        await bot.send_message(int(get_account_id()), body[:3900], reply_markup=markup)
    except Exception:
        pass


async def _send_delete_notification(row):
    if not str(get_account_id()).isdigit() or get_setting("notify_deleted", "1") != "1":
        return
    username = row["username"] if "username" in row.keys() else None
    url = f"https://t.me/{username}" if username else f"tg://user?id={row['user_id']}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 فتح حساب الشخص", url=url)]])
    body = f"🗑️ تم حذف رسالة من الخاص\n\n👤 الاسم: {row['display_name'] or 'مستخدم'}\n🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n🆔 ID: {row['user_id']}\n\n💬 {row['text'] or '[' + (row['media_type'] or 'وسائط') + ']'}"
    try:
        await bot.send_message(int(get_account_id()), body[:3900], reply_markup=markup)
    except Exception:
        pass


async def _delete_range_exact(chat_id, start_id, end_id, control_ids):
    if end_id < start_id:
        raise ValueError("invalid_range")
    entity = await client.get_entity(chat_id)
    if not isinstance(entity, types.User):
        me = await client.get_me()
        try:
            perms = await client.get_permissions(entity, me)
        except Exception as exc:
            raise PermissionError("delete_messages") from exc
        if not getattr(perms, "is_creator", False) and not getattr(perms, "delete_messages", False):
            raise PermissionError("delete_messages")
    actual = []
    async for message in client.iter_messages(chat_id, min_id=start_id - 1, max_id=end_id + 1, reverse=True):
        if message.id >= start_id and message.id <= end_id:
            actual.append(int(message.id))
    ordered = sorted(set(actual).union(int(x) for x in control_ids if x))
    deleted = 0
    for offset in range(0, len(ordered), 100):
        batch = ordered[offset:offset + 100]
        try:
            await client.delete_messages(chat_id, batch)
            deleted += len(batch)
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
    sync_result = await sync_all_private_users()
    if not client.is_connected():
        await client.connect()
    refreshed = await refresh_mimic_profile()
    return {"mimic_refreshed": refreshed, "private_sync": sync_result, "connected": client.is_connected()}


@client.on(events.NewMessage(incoming=True))
async def incoming(event):
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
    if not event.is_private:
        return
    sender = await event.get_sender()
    if not sender or getattr(sender, "bot", False) or getattr(sender, "deleted", False):
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
            current = await client.get_messages(user_id, ids=ids)
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

    if lower == "بداية الحذف":
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

    if lower == "نهاية الحذف":
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
        await client.send_message(event.chat_id, f"✅ تم مسح {count} رسالة")
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
    audit_tick = 0
    while True:
        await asyncio.sleep(30)
        try:
            if not client.is_connected():
                async with WATCHDOG_LOCK:
                    await client.connect()
                    add_log("operation_log", "telethon_reconnect", "تمت إعادة الاتصال تلقائيًا")
            audit_tick += 1
            if audit_tick >= 2:
                audit_tick = 0
                await audit_recent_private_deletions()
        except Exception as exc:
            add_log("operation_log", "watchdog_error", f"{type(exc).__name__}: {exc}")


async def start_user_client():
    """Start every authorized Telegram account belonging to the allowed bot users."""
    init_database()
    # Preserve a legacy V1-V17 owner session when upgrading in-place.
    if ADMIN_ID and str(ADMIN_ID).isdigit():
        legacy = Path(__file__).resolve().parents[2] / 'special_user.session'
        new_session = Path(__file__).resolve().parents[2] / 'storage' / 'accounts' / str(ADMIN_ID) / 'session' / 'telegram.session'
        if legacy.exists() and not new_session.exists():
            new_session.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(legacy, new_session)
            except Exception as exc:
                print(f"⚠️ تعذر ترحيل جلسة المالك القديمة: {type(exc).__name__}")
    ids = []
    if ADMIN_ID and str(ADMIN_ID).isdigit():
        ids.append(str(ADMIN_ID))
    try:
        ids.extend(str(r['user_id']) for r in get_allowed_users())
    except Exception:
        pass
    seen = set()
    for account_id in ids:
        if account_id in seen:
            continue
        seen.add(account_id)
        try:
            c = await manager.add_account(account_id)
            if c:
                me = await c.get_me()
                print(f"🟢 Special User Automation يعمل للحساب {me.id}")
            else:
                print(f"🟡 لا توجد جلسة دخول صالحة للحساب {account_id}")
        except Exception as exc:
            print(f"⚠️ تعذر تشغيل حساب {account_id}: {type(exc).__name__}: {exc}")
    # Keep the main task alive while per-account clients run in background tasks.
    while True:
        await asyncio.sleep(3600)


async def resolve_username(value):
    value = str(value).strip().lstrip("@")
    entity = await client.get_entity(value)
    if not hasattr(entity, "id") or getattr(entity, "bot", False) or getattr(entity, "deleted", False):
        return None
    if not isinstance(entity, types.User):
        return None
    return int(entity.id)
