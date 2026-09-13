from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.core.permissions import is_owner
from app.user.client import manager
from .context import session, clear

router = Router()

LOGIN_MODES = {
    'login_phone',
    'login_code',
    'login_password',
}


@router.message(Command('login'))
async def login(m: Message):
    if not is_owner(m.from_user.id):
        return await m.answer('⛔ هذا الأمر للمالك فقط')

    session(m.from_user.id).mode = 'login_phone'

    await m.answer(
        '📱 أرسل رقم الهاتف بصيغة دولية مثل +9665xxxxxxx\n'
        'لن يتم حفظ رمز Telegram أو كلمة مرور التحقق بخطوتين في قاعدة البيانات'
    )


@router.message(F.text)
async def login_flow(m: Message):
    if not is_owner(m.from_user.id):
        return

    s = session(m.from_user.id)

    # لا نتدخل في أي رسالة عادية إلا إذا كان المستخدم
    # فعلاً داخل إحدى خطوات تسجيل الدخول
    if s.mode not in LOGIN_MODES:
        return

    if s.mode == 'login_phone':
        await manager.send_code(m.text.strip())
        s.mode = 'login_code'
        await m.answer('📨 أرسل رمز Telegram الذي وصلك')

    elif s.mode == 'login_code':
        result = await manager.sign_in_code(m.text.strip())

        if result == 'PASSWORD_REQUIRED':
            s.mode = 'login_password'
            await m.answer(
                '🔐 الحساب عليه تحقق بخطوتين أرسل كلمة المرور مرة واحدة '
                'ولن أحفظها'
            )
        else:
            clear(m.from_user.id)
            await m.answer('✅ تم تسجيل حساب Telegram بنجاح')

    elif s.mode == 'login_password':
        await manager.sign_in_password(m.text)
        clear(m.from_user.id)
        await m.answer('✅ تم تسجيل الحساب بنجاح')
