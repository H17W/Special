from aiogram import Router, F
from aiogram.types import CallbackQuery

from .keyboards import main_menu, automation_menu
from app.user.moderation import muted_users


router = Router()


@router.callback_query(F.data == "automation")
async def automation_callback(callback: CallbackQuery):
    await callback.answer()

    users = muted_users()

    await callback.message.edit_text(
        "🧠 User Automation\n\n"
        f"🔇 عدد المستخدمين المكتومين: {len(users)}",
        reply_markup=automation_menu(),
    )


@router.callback_query(F.data == "muted_list")
async def muted_list_callback(callback: CallbackQuery):
    await callback.answer()

    users = muted_users()

    if not users:
        text = (
            "👥 المكتومون\n\n"
            "لا يوجد مستخدمون مكتومون."
        )
    else:
        lines = ["👥 المكتومون", ""]

        for user in users:
            name = user["display_name"] or "Unknown"
            username = user["username"]

            if username:
                lines.append(f"🔇 {name} — @{username}")
            else:
                lines.append(f"🔇 {name}")

            lines.append(f"ID: {user['user_id']}")
            lines.append("")

        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=automation_menu(),
    )


@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "🧠 أهلاً بك في Special\n\n"
        "لوحة التحكم الرئيسية:",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "private")
async def private_callback(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "📥 إدارة الخاص\n\n"
        "سيتم ربط وظائف إدارة الخاص هنا.",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "storage")
async def storage_callback(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "🗃 التخزين\n\n"
        "قاعدة البيانات تعمل حاليًا.",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "protection")
async def protection_callback(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "🛡 الحماية\n\n"
        "إعدادات الحماية سيتم ربطها هنا.",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "settings")
async def settings_callback(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "⚙️ الإعدادات\n\n"
        "إعدادات النظام سيتم ربطها هنا.",
        reply_markup=main_menu(),
    )
