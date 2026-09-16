import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.core.config import BOT_TOKEN
from app.core.database import init_database
from app.core.security import validate_runtime_security
from app.bot.login import router as login_router
from app.bot.handlers import router as handlers_router
from app.bot.callbacks import router as callbacks_router
from app.user.client import start_user_client, start_all_authorized_users

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


async def run_bot():
    validate_runtime_security(BOT_TOKEN, __import__("app.core.config", fromlist=["API_ID"]).API_ID, __import__("app.core.config", fromlist=["API_HASH"]).API_HASH, __import__("app.core.config", fromlist=["ADMIN_ID"]).ADMIN_ID)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(login_router)
    dp.include_router(handlers_router)
    dp.include_router(callbacks_router)
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"🟢 Special Bot يعمل: @{me.username} | ID: {me.id}")
    print("🟢 Special Bot ينتظر الرسائل...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


async def main():
    init_database()
    user_task = asyncio.create_task(start_user_client())
    await start_all_authorized_users()
    try:
        await run_bot()
    finally:
        user_task.cancel()
        try:
            await user_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
