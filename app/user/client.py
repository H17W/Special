from telethon import TelegramClient, events

from app.core.config import API_ID, API_HASH
from app.core.database import init_database
from app.user.moderation import check_muted, mute, unmute


client = TelegramClient(
    "special_user",
    int(API_ID),
    API_HASH,
)


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
        await event.delete()
    except Exception:
        pass


@client.on(events.NewMessage(outgoing=True))
async def outgoing_command(event):
    if not event.is_private:
        return

    text = (event.raw_text or "").strip().lower()

    # كتم بالرد
    if text in {".كتم", "كتم", "/كتم", ".mute", "mute"}:
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
            or getattr(target, "title", None)
            or "مستخدم"
        )

        username = getattr(target, "username", None)

        mute(
            user_id=target.id,
            username=username,
            display_name=name,
        )

        await event.edit(
            "🔇 تم كتم المستخدم بنجاح.\n\n"
            f"الاسم: {name}\n"
            f"ID: {target.id}"
        )

        return

    # إلغاء الكتم بالرد
    if text in {".فك", "فك", "/فك", ".unmute", "unmute"}:
        if not event.is_reply:
            await event.edit(
                "⚠️ رد على رسالة المستخدم أولًا ثم أرسل أمر فك الكتم."
            )
            return

        replied = await event.get_reply_message()

        if replied is None:
            return

        target = await replied.get_sender()

        if target is None:
            return

        removed = unmute(target.id)

        if removed:
            await event.edit(
                "🔊 تم إلغاء كتم المستخدم بنجاح."
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
