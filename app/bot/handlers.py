from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.core.config import ADMIN_ID
from app.user.moderation import mute, unmute

from .keyboards import main_menu, automation_menu


router = Router()

waiting_for_mute = set()
waiting_for_unmute = set()


def is_admin(message: Message) -> bool:
    return ADMIN_ID and str(message.from_user.id) == str(ADMIN_ID)


@router.message(CommandStart())
async def start_handler(message: Message):
    if not is_admin(message):
        await message.answer("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    await message.answer(
        "🧠 أهلاً بك في Special\n\n"
        "لوحة التحكم الرئيسية:",
        reply_markup=main_menu(),
    )


@router.message()
async def text_handler(message: Message):
    if not is_admin(message):
        return

    user_id = message.from_user.id

    if user_id in waiting_for_mute:
        waiting_for_mute.discard(user_id)

        try:
            target_id = int(message.text.strip())
        except (ValueError, AttributeError):
            await message.answer(
                "❌ المعرف غير صحيح.\n\n"
                "أرسل Telegram ID رقمي فقط."
            )
            return

        mute(
            user_id=target_id,
            username=None,
            display_name=None,
        )

        await message.answer(
            "🔇 تم كتم المستخدم.\n\n"
            f"ID: {target_id}",
            reply_markup=automation_menu(),
        )
        return

    if user_id in waiting_for_unmute:
        waiting_for_unmute.discard(user_id)

        try:
            target_id = int(message.text.strip())
        except (ValueError, AttributeError):
            await message.answer(
                "❌ المعرف غير صحيح.\n\n"
                "أرسل Telegram ID رقمي فقط."
            )
            return

        removed = unmute(target_id)

        if removed:
            text = (
                "🔊 تم إلغاء كتم المستخدم.\n\n"
                f"ID: {target_id}"
            )
        else:
            text = (
                "ℹ️ هذا المستخدم غير موجود في قائمة المكتومين.\n\n"
                f"ID: {target_id}"
            )

        await message.answer(
            text,
            reply_markup=automation_menu(),
        )
