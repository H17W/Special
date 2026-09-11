import json
import re
import tempfile
from datetime import datetime
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telethon import TelegramClient, events, functions

from app.core.config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from app.core.database import *
from app.user.moderation import check_muted, mute, unmute

client = TelegramClient("special_user", int(API_ID), API_HASH)
bot = Bot(token=BOT_TOKEN)
MEDIA_ROOT = Path(__file__).resolve().parents[2] / "storage" / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
PROFILE_ROOT = Path(__file__).resolve().parents[2] / "storage" / "profile_mimic"
PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
PROFILE_BACKUP = PROFILE_ROOT / "backup.json"
RANGE_STARTS = {}


def media_type(message):
    if not message.media:
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
    if not event.message.media:
        return None
    folder = MEDIA_ROOT / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return await event.download_media(file=str(folder / f"{direction}_{event.id}"))
    except Exception:
        return None


async def send_text_chunks(text):
    for i in range(0, len(text or ""), 4000):
        await bot.send_message(int(ADMIN_ID), text[i:i + 4000])


async def save_replied_media(event, replied, sender):
    """Save media only when the owner replies to that media with any text/character."""
    if not replied or not replied.media or not ADMIN_ID:
        return False

    name = getattr(sender, "first_name", None) or getattr(sender, "last_name", None) or getattr(sender, "title", None) or "مستخدم"
    username = getattr(sender, "username", None)
    username_text = f"@{username}" if username else "لا يوجد يوزر"
    user_url = f"https://t.me/{username}" if username else f"tg://user?id={sender.id}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👤 فتح المستخدم", url=user_url)
    ]])

    ttl = getattr(replied, "ttl_period", None)
    temporary = "\n⏳ وسائط مؤقتة" if ttl else ""
    caption = (
        f"📥 تم حفظ وسائط من الخاص{temporary}\n\n"
        f"👤 الاسم: {name}\n"
        f"🆔 ID: {sender.id}\n"
        f"🔗 Username: {username_text}\n"
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

        add_log(
            "operation_log",
            "reply_media_saved",
            f"تم حفظ وسائط بالرد من {sender.id} (message={replied.id})"
        )
        return True
    except Exception as exc:
        add_log(
            "operation_log",
            "reply_media_save_failed",
            f"فشل حفظ الوسائط بالرد ID={replied.id}: {type(exc).__name__}"
        )
        return False
    finally:
        for item in temp_dir.iterdir():
            if item.is_file():
                item.unlink(missing_ok=True)
        temp_dir.rmdir()


def _profile_name(user):
    first = (getattr(user, "first_name", None) or "").strip()
    last = (getattr(user, "last_name", None) or "").strip()
    return first, last


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
        photos = await client.get_profile_photos(me, limit=10)
        if photos:
            await client(functions.photos.DeletePhotosRequest(id=list(photos)))
    except Exception as exc:
        add_log("operation_log", "profile_photo_delete_failed", f"فشل حذف صور الملف الشخصي: {type(exc).__name__}")


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
        "created_at": datetime.utcnow().isoformat(),
    }

    photos = await client.get_profile_photos(me, limit=1)
    if photos:
        photo_path = PROFILE_ROOT / "original_profile_photo"
        downloaded = await client.download_media(photos[0], file=str(photo_path))
        if downloaded:
            backup["photo"] = str(downloaded)

    _save_profile_backup(backup)
    return backup


async def _resolve_target_from_command(event):
    if event.is_reply:
        replied = await event.get_reply_message()
        if replied:
            sender = await replied.get_sender()
            if sender:
                return sender

    match = re.search(r"@([A-Za-z0-9_]{3,32})", event.raw_text or "")
    if match:
        try:
            return await client.get_entity(match.group(1))
        except Exception:
            return None
    return None


async def mimic_user(event, target):
    backup = await _backup_current_profile()
    first, last = _profile_name(target)
    about = getattr(target, "about", None) or ""

    await client(functions.account.UpdateProfileRequest(
        first_name=first or "Special",
        last_name=last,
        about=about,
    ))

    photos = await client.get_profile_photos(target, limit=1)
    if photos:
        temp_dir = Path(tempfile.mkdtemp(prefix="special_mimic_"))
        try:
            path = await client.download_media(photos[0], file=str(temp_dir / "target_profile"))
            if path:
                uploaded = await client.upload_file(path)
                await client(functions.photos.UploadProfilePhotoRequest(file=uploaded))
        finally:
            for item in temp_dir.iterdir():
                if item.is_file():
                    item.unlink(missing_ok=True)
            temp_dir.rmdir()

    add_log("operation_log", "profile_mimic_started", f"تم تقليد المستخدم {target.id}")
    return backup


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
    photo = backup.get("photo")
    if photo and Path(photo).exists():
        uploaded = await client.upload_file(photo)
        await client(functions.photos.UploadProfilePhotoRequest(file=uploaded))

    backup["active"] = False
    _save_profile_backup(backup)
    add_log("operation_log", "profile_mimic_stopped", "تم استعادة بيانات الملف الشخصي الأصلية")
    return True


async def delete_message_range(chat_id, start_id, end_id):
    if end_id < start_id:
        return 0
    messages = []
    async for msg in client.iter_messages(chat_id, min_id=start_id - 1, max_id=end_id + 1, limit=None):
        if start_id <= msg.id <= end_id:
            messages.append(msg.id)
    if not messages:
        return 0
    messages = sorted(set(messages))
    deleted = 0
    for i in range(0, len(messages), 100):
        batch = messages[i:i + 100]
        result = await client.delete_messages(chat_id, batch)
        deleted += len(result or batch)
    return deleted


async def send_deleted_message_log(event, sender):
    name = getattr(sender, "first_name", None) or getattr(sender, "last_name", None) or getattr(sender, "title", None) or "مستخدم"
    username = getattr(sender, "username", None)
    info = f"🔇 تم حذف رسالة من مستخدم مكتوم\n\n👤 الاسم: {name}\n🆔 ID: {sender.id}\n🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}"
    await bot.send_message(int(ADMIN_ID), info)
    if event.raw_text:
        await send_text_chunks(f"💬 الرسالة:\n\n{event.raw_text}")
    if not event.message.media:
        return
    temp = Path(tempfile.mkdtemp(prefix="special_deleted_"))
    try:
        path = await event.download_media(file=str(temp))
        if not path:
            return
        f = FSInputFile(path)
        if event.message.photo:
            await bot.send_photo(int(ADMIN_ID), f)
        elif event.message.video:
            await bot.send_video(int(ADMIN_ID), f)
        elif event.message.voice:
            await bot.send_voice(int(ADMIN_ID), f)
        elif event.message.audio:
            await bot.send_audio(int(ADMIN_ID), f)
        else:
            await bot.send_document(int(ADMIN_ID), f)
    finally:
        for p in temp.iterdir():
            p.unlink(missing_ok=True)
        temp.rmdir()


@client.on(events.NewMessage(incoming=True))
async def incoming(event):
    if not event.is_private:
        return
    sender = await event.get_sender()
    if not sender:
        return
    name = getattr(sender, "first_name", None) or getattr(sender, "last_name", None) or "مستخدم"
    username = getattr(sender, "username", None)
    upsert_private_chat(sender.id, username, name)
    mt = media_type(event.message)
    media_path = await archive_media(event, sender.id, "in")
    add_message(event.id, sender.id, event.chat_id, "incoming", event.raw_text, mt, media_path, str(event.date))
    increment_stats(sender.id, mt, has_link(event.raw_text))

    if check_muted(sender.id):
        try:
            mark_message_deleted(event.id, event.chat_id, "incoming")
            await send_deleted_message_log(event, sender)
        except Exception:
            pass
        try:
            await event.delete()
        except Exception:
            pass


@client.on(events.MessageEdited(incoming=True))
async def incoming_edit(event):
    if not event.is_private:
        return
    mark_message_edited(event.id, event.chat_id, "incoming", event.raw_text)
    add_log("operation_log", "message_edited", f"تم تعديل رسالة واردة ID={event.id} في chat={event.chat_id}")


@client.on(events.MessageEdited(outgoing=True))
async def outgoing_edit(event):
    if not event.is_private:
        return
    mark_message_edited(event.id, event.chat_id, "outgoing", event.raw_text)
    add_log("operation_log", "message_edited", f"تم تعديل رسالة صادرة ID={event.id} في chat={event.chat_id}")


@client.on(events.NewMessage(outgoing=True))
async def outgoing(event):
    if not event.is_private:
        return
    target = await event.get_chat()
    if not target:
        return
    name = getattr(target, "first_name", None) or getattr(target, "last_name", None) or "مستخدم"
    username = getattr(target, "username", None)
    upsert_private_chat(target.id, username, name)
    mt = media_type(event.message)
    media_path = await archive_media(event, target.id, "out")
    add_message(event.id, target.id, event.chat_id, "outgoing", event.raw_text, mt, media_path, str(event.date))
    increment_stats(target.id, mt, has_link(event.raw_text))

    # حفظ الوسائط فقط عند الرد عليها من حساب المالك بأي حرف أو كلمة أو حركة
    # ولا يتم إرسال الرسائل النصية العادية إلى البوت.
    if event.is_reply:
        replied = await event.get_reply_message()
        if replied and replied.media:
            await save_replied_media(event, replied, target)

    text = (event.raw_text or "").strip().lower()

    if text in {"/بداية", "بداية"}:
        if not event.is_reply:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        replied = await event.get_reply_message()
        if not replied:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        RANGE_STARTS[event.chat_id] = replied.id
        await event.edit("✅ تم تحديد الرسالة")
        return

    if text in {"/نهاية", "نهاية"}:
        if not event.is_reply:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        replied = await event.get_reply_message()
        if not replied:
            await event.edit("❌ فشلت العملية يجب الرد على الرسالة للتحديد")
            return
        start_id = RANGE_STARTS.get(event.chat_id)
        if start_id is None:
            await event.edit("❌ فشلت العملية يجب تحديد رسالة البداية أولًا")
            return
        end_id = replied.id
        if end_id < start_id:
            await event.edit("❌ فشلت العملية يجب أن تكون رسالة النهاية بعد البداية")
            return
        count = await delete_message_range(event.chat_id, start_id, end_id)
        RANGE_STARTS.pop(event.chat_id, None)
        await event.edit(f"✅ تم مسح {count} رسالة بنجاح")
        return

    if text in {"تقليد", "/تقليد"}:
        target = await _resolve_target_from_command(event)
        if not target:
            await event.edit("❌ فشلت العملية يجب الرد على المستخدم أو كتابة منشنه")
            return
        existing = _load_profile_backup()
        if existing and existing.get("active"):
            await event.edit("ℹ️ التقليد مفعّل بالفعل ألغِ التقليد أولًا")
            return
        await mimic_user(event, target)
        target_name = getattr(target, "first_name", None) or getattr(target, "last_name", None) or "المستخدم"
        await event.edit(f"✅ تم تقليد {target_name} بنجاح")
        return

    if text in {"الغاء التقليد", "إلغاء التقليد", "/الغاء التقليد", "/إلغاء التقليد"}:
        if await restore_profile():
            await event.edit("✅ تم إلغاء التقليد واستعادة حسابك مثل ما كان")
        else:
            await event.edit("ℹ️ ما فيه تقليد مفعّل حاليًا")
        return

    if text in {".كتم", "كتم", "/كتم", ".mute", "mute"}:
        if not event.is_reply:
            await event.edit("⚠️ رد على رسالة المستخدم أولًا ثم أرسل أمر الكتم.")
            return
        replied = await event.get_reply_message()
        target2 = await replied.get_sender() if replied else None
        if not target2:
            await event.edit("⚠️ لم أستطع تحديد صاحب الرسالة.")
            return
        name2 = getattr(target2, "first_name", None) or getattr(target2, "last_name", None) or "مستخدم"
        user2 = getattr(target2, "username", None)
        mute(target2.id, user2, name2)
        await event.edit(f"🔇 تم كتم المستخدم بنجاح.\n\nالاسم: {name2}\nID: {target2.id}\nUsername: {('@' + user2) if user2 else 'لا يوجد يوزر'}")
    elif text in {".فك", "فك", "/فك", ".unmute", "unmute", "الغاء الكتم", "إلغاء الكتم", "/الغاء الكتم", "/إلغاء الكتم"}:
        if not event.is_reply:
            await event.edit("⚠️ رد على رسالة المستخدم أولًا ثم أرسل أمر إلغاء الكتم.")
            return
        replied = await event.get_reply_message()
        target2 = await replied.get_sender() if replied else None
        if not target2:
            await event.edit("⚠️ لم أستطع تحديد صاحب الرسالة.")
            return
        await event.edit("🔊 تم إلغاء الكتم عن المستخدم بنجاح." if unmute(target2.id) else "ℹ️ المستخدم غير موجود في قائمة المكتومين.")


async def start_user_client():
    init_database()
    await client.start()
    me = await client.get_me()
    print("🟢 Special User Automation يعمل")
    print(f"الحساب: {me.first_name}")
    print(f"ID: {me.id}")
    await client.run_until_disconnected()
