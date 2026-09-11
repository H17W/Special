import os

from telethon import TelegramClient, events

from app.core.database import init_database
from app.user.moderation import check_muted


API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

client = TelegramClient(
    "special_user",
    API_ID,
    API_HASH,
)


@client.on(events.NewMessage(incoming=True))
async def incoming_message(event):
    if not event.is_private:
        return

    sender = await event.get_sender()

    if sender is None:
        return

    user_id = sender.id

    if not check_muted(user_id):
        return

    try:
        await event.delete()
    except Exception:
        pass


async def main():
    init_database()

    me = await client.get_me()

    print("🟢 Special User Automation يعمل")
    print(f"الحساب: {me.first_name}")
    print(f"ID: {me.id}")
    print("في انتظار الرسائل...")


with client:
    client.loop.run_until_complete(main())
    client.run_until_disconnected()
