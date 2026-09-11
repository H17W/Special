import os
import tempfile
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from telethon import TelegramClient, events

from app.core.config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from app.core.database import init_database
from app.user.moderation import check_muted, mute, unmute


client = TelegramClient(
    "special_user",
    int(API_ID),
    API_HASH,
)

bot = Bot(token=BOT_TOKEN)


async def send_text_chunks(text: str):
    if not text:
        return

    max_length = 4000

    for i in range(0, len(text), max_length):
        await bot.send_message(
            chat_id=int(ADMIN_ID),
            text=text[i:i + max_length],
        )


async def send_deleted_message_log(event, sender):
    name = (
        getattr(sender, "first_name", None)
        or getattr(sender, "last_name", None)
        or getattr(sender, "title", None)
        or "مستخدم"
    )

    username = getattr(sender, "username", None)
    username_text = f"@{username}" if username else "لا يوجد يوزر"

    user_id = sender.id

    info = (
        "🔇 تم حذف رسالة من مستخدم مكتوم\n\n"
        f"👤 الاسم: {name}\n"
        f"🆔 ID: {user_id}\n"
        f"🔗 Username: {username_text}"
    )

    await bot.send_message(
        chat_id=int(ADMIN_ID),
        text=info,
    )

    if event.raw_text:
        await send_text_chunks(
            f"💬 الرسالة:\n\n{event.raw_text}"
        )

    if not event.message.media:
        return

    temp_dir = Path(tempfile.mkdtemp(prefix="special_deleted_"))

    try:
        media_path = await event.download_media(
            file=str(temp_dir)
        )

        if not media_path:
            return

        file_path = Path(media_path)
        input_file = FSInputFile(file_path)

        if event.message.photo:
            await bot.send_photo(
                chat_id=int(ADMIN_ID),
                photo=input_file,
            )

        elif event.message.video:
            await bot.send_video(
                chat_id=int(ADMIN_ID),
                video=input_file,
            )

        elif event.message.voice:
            await bot.send_voice(
                chat_id=int(ADMIN_ID),
                voice=input_file,
            )

        elif event.message.audio:
            await bot.send_audio(
                chat_id=int(ADMIN_ID),
                audio=input_file,
            )

        else:
            await bot.send_document(
                chat_id=int(ADMIN_ID),
                document=input_file,
            )

    finally:
        try:
            for file in temp_dir.iterdir():
                file.unlink(missing_ok=True)

            temp_dir.rmdir()

        except Exception:
            pass


@client.on(events.NewMessage(incoming=True))
async def incoming_message(event):
    if not event.is_private:
        return

    sender = await event.get_sender()

    if sender is None:
        return

    if not check_muted(sender.id):
        return

    try:
        await send_deleted_message_log(event, sender)
    except Exception:
        pass

    try:
        await event.delete()
    except Exception:
        pass


@client.on(events.NewMessage(outgoing=True))
async def outgoing_command(event):
    if not event.is_private:
        return

    text = (event.raw_text or "").strip().lower()

    # ==============================
    # كتم بالرد
    # ==============================

    if text in {
        ".كتم",
        "كتم",
        "/كتم",
        ".mute",
        "mute",
    }:

        if not event.is_reply:
            await event.edit(
                "⚠️ رد على رسالة المستخدم أولًا ثم أرسل أمر الكتم."
            )
            return

        replied = await event.get_reply_message()

        if replied is None:
            await event.edit(
                "⚠️ لم أستطع العثور على الرسالة التي رددت عليها."
            )
            return

        target = await replied.get_sender()

        if target is None:
            await event.edit(
                "⚠️ لم أستطع تحديد صاحب الرسالة."
            )
            return

        name = (
            getattr(target, "first_name", None)
            or getattr(target, "last_name", None)
            or getattr(target, "title", None)
            or "مستخدم"
        )

        username = getattr(target, "username", None)

        mute(
            user_id=target.id,
            username=username,
            display_name=name,
        )

        username_text = (
            f"@{username}"
            if username
            else "لا يوجد يوزر"
        )

        await event.edit(
            "🔇 تم كتم المستخدم بنجاح.\n\n"
            f"الاسم: {name}\n"
            f"ID: {target.id}\n"
            f"Username: {username_text}"
        )

        return

    # ==============================
    # إلغاء الكتم بالرد
    # ==============================

    if text in {
        ".فك",
        "فك",
        "/فك",
        ".unmute",
        "unmute",
        "الغاء الكتم",
        "إلغاء الكتم",
        "/الغاء الكتم",
        "/إلغاء الكتم",
    }:

        if not event.is_reply:
            await event.edit(
                "⚠️ رد على رسالة المستخدم أولًا ثم أرسل أمر إلغاء الكتم."
            )
            return

        replied = await event.get_reply_message()

        if replied is None:
            await event.edit(
                "⚠️ لم أستطع العثور على الرسالة التي رددت عليها."
            )
            return

        target = await replied.get_sender()

        if target is None:
            await event.edit(
                "⚠️ لم أستطع تحديد صاحب الرسالة."
            )
            return

        removed = unmute(target.id)

        if removed:
            await event.edit(
                "🔊 تم إلغاء الكتم عن المستخدم بنجاح."
            )
        else:
            await event.edit(
                "ℹ️ المستخدم غير موجود في قائمة المكتومين."
            )


async def start_user_client():
    init_database()

    await client.start()

    me = await client.get_me()

    print("🟢 Special User Automation يعمل")
    print(f"الحساب: {me.first_name}")
    print(f"ID: {me.id}")

    await client.run_until_disconnected()
