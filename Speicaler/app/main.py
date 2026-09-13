from __future__ import annotations
import asyncio
from aiogram import Bot, Dispatcher
from app.core.config import settings
from app.core.logger import log
from app.core.database import db
from app.user.worker import start_user_client
from app.bot.handlers import router as handlers_router
from app.bot.callbacks import router as callbacks_router
from app.bot.admin_commands import router as admin_router
from app.bot.login import router as login_router

async def main():
    missing=settings.validate()
    if missing: raise RuntimeError('Missing environment variables: '+', '.join(missing))
    await start_user_client()
    bot=Bot(settings.bot_token); dp=Dispatcher()
    async def maintenance():
        while True:
            try: db.cleanup_expired()
            except Exception as exc: log.warning('maintenance failed: %s', exc)
            await asyncio.sleep(60)
    maintenance_task=asyncio.create_task(maintenance())
    dp.include_router(login_router); dp.include_router(admin_router); dp.include_router(callbacks_router); dp.include_router(handlers_router)
    log.info('Special started')
    try: await dp.start_polling(bot)
    finally:
        maintenance_task.cancel()
        try: await maintenance_task
        except asyncio.CancelledError: pass
        await bot.session.close()
        await __import__('app.user.worker',fromlist=['stop_user_client']).stop_user_client()

if __name__=='__main__': asyncio.run(main())
