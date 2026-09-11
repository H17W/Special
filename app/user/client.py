import os
from telethon import TelegramClient


API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

client = TelegramClient("special_user", API_ID, API_HASH)


async def main():
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} | ID: {me.id}")


with client:
    client.loop.run_until_complete(main())
