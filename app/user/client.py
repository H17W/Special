import os

from telethon import TelegramClient, events


API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

client = TelegramClient("special_user", API_ID, API_HASH)


@client.on(events.NewMessage(incoming=True))
async def incoming_message(event):
    sender = await event.get_sender()

    if sender is None:
        return

    name = getattr(sender, "first_name", None) or getattr(sender, "title", None) or "Unknown"
    username = getattr(sender, "username", None)
    user_id = sender.id

    print(
        "\n📩 رسالة واردة"
        f"\nالاسم: {name}"
        f"\nUsername: @{username}" if username else ""
    )

    print(f"ID: {user_id}")

    if event.raw_text:
        print(f"النص: {event.raw_text}")
    else:
        print("المحتوى: رسالة بدون نص")


async def main():
    me = await client.get_me()

    print("🟢 Special User Automation يعمل")
    print(f"الحساب: {me.first_name}")
    print(f"ID: {me.id}")
    print("في انتظار الرسائل...")


with client:
    client.loop.run_until_complete(main())
    client.run_until_disconnected()
