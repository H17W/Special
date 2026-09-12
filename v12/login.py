import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv(override=True)

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")


async def main():
    phone = input("Phone: ").strip()

    client = TelegramClient("special_user", API_ID, API_HASH)

    try:
        await client.connect()

        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ الحساب مسجل دخول بالفعل: {me.id}")
            return

        await client.send_code_request(phone)
        code = input("Telegram code: ").strip()

        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            password = input("Two-step verification password: ")
            await client.sign_in(password=password)

        me = await client.get_me()

        print("✅ تم تسجيل الدخول بنجاح")
        print(f"الاسم: {me.first_name or ''}")
        print(f"ID: {me.id}")

    except Exception as e:
        print(f"❌ فشل تسجيل الدخول: {type(e).__name__}: {e}")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
