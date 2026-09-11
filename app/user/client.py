from telethon import TelegramClient, events

from app.core.config import API_ID, API_HASH
from app.core.database import init_database
from app.user.moderation import check_muted


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


async def start_user_client():
    init_database()

    await client.start()

    me = await client.get_me()

    print("🟢 Special User Automation يعمل")
    print(f"الحساب: {me.first_name}")
    print(f"ID: {me.id}")

    await client.run_until_disconnected()
