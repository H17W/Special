from __future__ import annotations

import asyncio
import time

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message

from app.core.config import settings
from app.core.database import db
from app.core.logger import log
from app.user.worker import start_user_client
from app.bot.keyboards import main_menu, access_request
from app.bot.callbacks import router as callbacks_router
from app.bot.admin_commands import router as admin_router
from app.bot.handlers import router as handlers_router
from app.bot.login import router as login_router


root_router = Router(name='root')


@root_router.message(F.text.regexp(r'^/start(?:@\w+)?(?:\s.*)?$'))
async def start(message: Message):
    if not message.from_user:
        return

    uid = message.from_user.id
    db.upsert_user(uid, message.from_user.username, message.from_user.first_name)

    payload = ''
    parts = (message.text or '').split(maxsplit=1)
    if len(parts) == 2:
        payload = parts[1].strip()

    if payload and not db.access_active(uid):
        linked = db.consume_link(payload)
        if linked is not None:
            _target_user_id, grant_seconds = linked
            now = int(time.time())
            db.run(
                'UPDATE users SET status=\'active\', expires_at=?, updated_at=? WHERE id=?',
                (now + grant_seconds, now, uid),
            )

    if not db.unrestricted(uid):
        rem = db.remaining_restriction(uid)
        await message.answer(
            '⛔ حسابك مقيّد حالياً.'
            + (f' المدة المتبقية {rem} ثانية.' if rem > 0 else '')
        )
        return

    if not settings.owner_id:
        await message.answer('❌ OWNER_ID غير مضبوط')
        return

    if uid != settings.owner_id and not db.access_active(uid):
        await message.answer(
            '⛔ غير مصرح لك باستخدام Special.',
            reply_markup=access_request(),
        )
        return

    await message.answer(
        '🧠 أهلاً بك في Special\n\nاختر من لوحة التحكم:',
        reply_markup=main_menu(uid == settings.owner_id),
    )


async def main():
    missing = settings.validate()
    if missing:
        raise RuntimeError('Missing environment variables: ' + ', '.join(missing))

    # User-account automation is optional for bot startup. A failed user-session
    # startup must not prevent the bot UI from responding to /start.
    try:
        await start_user_client()
    except Exception as exc:
        log.exception('user client startup failed: %s', exc)

    bot = Bot(settings.bot_token)
    dp = Dispatcher()

    async def maintenance():
        while True:
            try:
                db.cleanup_expired()
            except Exception as exc:
                log.warning('maintenance failed: %s', exc)
            await asyncio.sleep(60)

    maintenance_task = asyncio.create_task(maintenance())

    # Start must be registered first so no generic text handler can swallow /start.
    dp.include_router(root_router)
    dp.include_router(login_router)
    dp.include_router(admin_router)
    dp.include_router(callbacks_router)
    dp.include_router(handlers_router)

    log.info('Special started')
    log.info('Owner ID loaded: %s', settings.owner_id)

    try:
        await dp.start_polling(bot)
    finally:
        maintenance_task.cancel()
        try:
            await maintenance_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        await __import__('app.user.worker', fromlist=['stop_user_client']).stop_user_client()


if __name__ == '__main__':
    asyncio.run(main())
