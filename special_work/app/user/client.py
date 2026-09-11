import re
import tempfile
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from telethon import TelegramClient, events

from app.core.config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from app.core.database import *
from app.user.moderation import check_muted, mute, unmute

client = TelegramClient("special_user", int(API_ID), API_HASH)
bot = Bot(token=BOT_TOKEN)
MEDIA_ROOT = Path(__file__).resolve().parents[2] / "storage" / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)


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

    text = (event.raw_text or "").strip().lower()
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
