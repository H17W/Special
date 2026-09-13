from __future__ import annotations
import asyncio
from aiogram import Bot,Dispatcher
from app.core.config import settings
from app.core.database import db
from app.core.logger import log
from app.core.queue import queue
from app.user.worker import start_user_client,stop_user_client
from app.bot.handlers import router as handlers_router
from app.bot.callbacks import router as callbacks_router
from app.bot.admin_commands import router as admin_router
async def main():
 missing=settings.validate()
 if missing: raise RuntimeError('Missing environment variables: '+', '.join(missing))
 await start_user_client(); await queue.start(); bot=Bot(settings.bot_token); dp=Dispatcher(); dp.include_router(admin_router); dp.include_router(callbacks_router); dp.include_router(handlers_router); log.info('Special v27 started')
 async def maintenance():
  while True:
   try: db.cleanup_expired()
   except Exception as e: log.warning('maintenance: %s',e)
   await asyncio.sleep(60)
 task=asyncio.create_task(maintenance())
 try: await dp.start_polling(bot)
 finally:
  task.cancel(); await queue.stop(); await stop_user_client(); await bot.session.close()
if __name__=='__main__': asyncio.run(main())
