import os

from telethon import TelegramClient, events

from app.user.moderation import mute, check_muted


API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

client = TelegramClient("special_user", API_ID, API_HASH)


@client.on(events.NewMessage)
async def message_handler(event):
    # تجاهل رسائل المجموعات والقنوات حاليًا
    if not event.is_private:
        return

    # ---------------------------------
    # أوامر الحساب الشخصي
    # ---------------------------------
    if event.out:
        text = (event.raw_text or "").strip()

        if text == "كتم":
            if not event.is_reply:
                print("⚠️ استخدم «كتم» بالرد على رسالة الشخص.")
                return

            replied_message = await event.get_reply_message()

            if not replied_message:
                return

            target = await replied_message.get_sender()

            if not target:
                return

            username = getattr(target, "username", None)
            display_name = (
                getattr(target, "first_name", None)
                or getattr(target, "title", None)
                or "Unknown"
            )

            mute(
                user_id=target.id,
                username=username,
                display_name=display_name,
            )

            print("\n🔇 تم كتم المستخدم")
            print(f"الاسم: {display_name}")
            print(f"ID: {target.id}")

            return

    # ---------------------------------
    # الرسائل الواردة
    # ---------------------------------
    if not event.out:
    sender = await event.get_sender()


        if sender is None:
            return

        user_id = sender.id

        name = (
            getattr(sender, "first_name", None)
            or getattr(sender, "title", None)
            or "Unknown"
        )

        username = getattr(sender, "username", None)

        print("\n📩 رسالة واردة")
        print(f"الاسم: {name}")
        print(f"Username: @{username}" if username else "Username: لا يوجد")
        print(f"ID: {user_id}")

        if event.raw_text:
            print(f"النص: {event.raw_text}")
        else:
            print("المحتوى: رسالة بدون نص")

        # ---------------------------------
        # فحص الكتم
        # ---------------------------------
        if check_muted(user_id):
            print("🔇 المستخدم مكتوم.")
            return


async def main():
    me = await client.get_me()

    print("🟢 Special User Automation يعمل")
    print(f"الحساب: {me.first_name}")
    print(f"ID: {me.id}")
    print("في انتظار الرسائل...")


with client:
    client.loop.run_until_complete(main())
    client.run_until_disconnected()
