from aiogram import Router, F
from aiogram.types import CallbackQuery


router = Router()


@router.callback_query(F.data == "automation")
async def automation_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🧠 User Automation\n\n"
        "الوحدة موجودة، وسيتم ربط وظائفها تدريجيًا."
    )


@router.callback_query(F.data == "private")
async def private_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📥 إدارة الخاص\n\n"
        "الوحدة موجودة، وسيتم ربط وظائفها تدريجيًا."
    )


@router.callback_query(F.data == "storage")
async def storage_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🗃 التخزين\n\n"
        "الوحدة موجودة، وسيتم ربط وظائفها تدريجيًا."
    )


@router.callback_query(F.data == "protection")
async def protection_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🛡 الحماية\n\n"
        "الوحدة موجودة، وسيتم ربط وظائفها تدريجيًا."
    )


@router.callback_query(F.data == "settings")
async def settings_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ الإعدادات\n\n"
        "الإعدادات الأساسية سيتم ربطها لاحقًا."
    )
