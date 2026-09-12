import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv(override=True)
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

async def main():
    phone = input("Phone: ").strip()
    client = TelegramClient("special_user", API_ID, API_HASH)
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"✅ الجلسة مسجلة مسبقًا: {me.id}")
        await client.disconnect()
        return
    await client.send_code_request(phone)
    code = input("Telegram code: ").strip()
    try:
        await client.sign_in(phone=phone, code=code)
    except Exception as exc:
        print(f"❌ فشل تسجيل الدخول: {type(exc).__name__}: {exc}")
        await client.disconnect()
        return
    me = await client.get_me()
    print(f"✅ تم تسجيل الدخول بنجاح: {me.id}")
    await client.disconnect()

asyncio.run(main())
