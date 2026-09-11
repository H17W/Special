import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.core.config import BOT_TOKEN
from app.core.database import init_database
from app.bot.handlers import router as handlers_router
from app.bot.callbacks import router as callbacks_router
from app.user.client import start_user_client


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


async def run_bot():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured.")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(handlers_router)
    dp.include_router(callbacks_router)

    # Polling and webhooks are mutually exclusive. Clear any webhook that may
    # have been left by another test/deployment before starting polling.
    await bot.delete_webhook(drop_pending_updates=False)

    me = await bot.get_me()
    print(f"🟢 Special Bot يعمل: @{me.username} | ID: {me.id}")
    print("🟢 Special Bot ينتظر الرسائل...")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()


async def main():
    init_database()

    # The user-account session must not be allowed to crash the bot polling.
    user_task = asyncio.create_task(start_user_client())
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
