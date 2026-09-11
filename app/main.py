import asyncio

from aiogram import Bot, Dispatcher

from app.core.config import BOT_TOKEN
from app.bot.handlers import router as handlers_router
from app.bot.callbacks import router as callbacks_router
from app.user.client import start_user_client


async def run_bot():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured.")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(handlers_router)
    dp.include_router(callbacks_router)

    print("🟢 Special Bot يعمل")

    await dp.start_polling(bot)


async def main():
    await asyncio.gather(
        run_bot(),
        start_user_client(),
    )


if __name__ == "__main__":
    asyncio.run(main())
