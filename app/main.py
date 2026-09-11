import asyncio

from aiogram import Bot, Dispatcher

from core.config import BOT_TOKEN
from bot.handlers import router as handlers_router
from bot.callbacks import router as callbacks_router


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured.")

    bot = Bot(token=BOT_TOKEN)

    dp = Dispatcher()

    dp.include_router(handlers_router)
    dp.include_router(callbacks_router)

    print("Special bot is starting...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
