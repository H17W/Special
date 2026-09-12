import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv(override=True)

API_ID_RAW = (os.getenv("API_ID") or "").strip()
API_HASH = (os.getenv("API_HASH") or "").strip()

if not API_ID_RAW:
    raise RuntimeError("API_ID غير موجود في ملف البيئة")

if not API_ID_RAW.isdigit():
    raise RuntimeError("API_ID يجب أن يكون رقمًا فقط")

if not API_HASH:
    raise RuntimeError("API_HASH غير موجود في ملف البيئة")

API_ID = int(API_ID_RAW)


async def main():
    phone = input("Phone: ").strip()

    if not phone:
        print("❌ يجب إدخال رقم الهاتف")
        return

    client = TelegramClient(
        "special_user",
        API_ID,
        API_HASH,
    )

    try:
        await client.connect()

        if await client.is_user_authorized():
            me = await client.get_me()

            print("✅ الجلسة مسجلة مسبقًا")
            print(f"الاسم: {me.first_name or ''}")
            print(f"ID: {me.id}")

            return

        await client.send_code_request(phone)

        code = input("Telegram code: ").strip()

        if not code:
            print("❌ لم يتم إدخال كود Telegram")
            return

        try:
            await client.sign_in(
                phone=phone,
                code=code,
            )

        except SessionPasswordNeededError:
            password = input(
                "Two-step verification password: "
            )

            if not password:
                print("❌ لم يتم إدخال كلمة مرور التحقق بخطوتين")
                return

            await client.sign_in(
                password=password
            )

        me = await client.get_me()

        print("✅ تم تسجيل الدخول بنجاح")
        print(f"الاسم: {me.first_name or ''}")
        print(f"ID: {me.id}")

    except Exception as exc:
        print(
            f"❌ فشل تسجيل الدخول: "
            f"{type(exc).__name__}: {exc}"
        )

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
