from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.core.config import ADMIN_ID
from app.user.moderation import muted_users

from .handlers import waiting_for_mute, waiting_for_unmute
from .keyboards import (
    main_menu,
    automation_menu,
    back_to_automation,
    private_menu,
    settings_menu,
)


router = Router()


def is_admin(callback: CallbackQuery) -> bool:
    return (
        ADMIN_ID
        and callback.from_user
        and str(callback.from_user.id) == str(ADMIN_ID)
    )


@router.callback_query(F.data == "automation")
async def automation_callback(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    users = muted_users()

    await callback.message.edit_text(
        "🧠 User Automation\n\n"
        f"🔇 عدد المستخدمين المكتومين: {len(users)}",
        reply_markup=automation_menu(),
    )

    await callback.answer()


@router.callback_query(F.data == "mute_user")
async def mute_user_callback(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    waiting_for_mute.add(callback.from_user.id)

    await callback.message.edit_text(
        "🔇 كتم مستخدم\n\n"
        "أرسل Telegram ID للمستخدم الذي تريد كتمه.",
        reply_markup=back_to_automation(),
    )

    await callback.answer()


@router.callback_query(F.data == "unmute_user")
async def unmute_user_callback(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    waiting_for_unmute.add(callback.from_user.id)

    await callback.message.edit_text(
        "🔊 إلغاء كتم\n\n"
        "أرسل Telegram ID للمستخدم الذي تريد إلغاء كتمه.",
        reply_markup=back_to_automation(),
    )

    await callback.answer()


@router.callback_query(F.data == "muted_list")
async def muted_list_callback(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    users = muted_users()

    if not users:
        text = (
            "👥 المكتومون\n\n"
            "لا يوجد مستخدمون مكتومون."
        )
    else:
        lines = [
            "👥 المكتومون",
            "",
        ]

        for user in users:
            name = user["display_name"] or "مستخدم"
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
        reply_markup=back_to_automation(),
    )

    await callback.answer()


@router.callback_query(F.data == "private")
async def private_callback(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "📥 إدارة الخاص\n\n"
        "من هنا تقدر تدخل إلى إدارة الكتم.",
        reply_markup=private_menu(),
    )

    await callback.answer()


@router.callback_query(F.data == "settings")
async def settings_callback(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "⚙️ الإعدادات\n\n"
        "إعدادات User Automation:",
        reply_markup=settings_menu(),
    )

    await callback.answer()


@router.callback_query(F.data == "storage")
async def storage_callback(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "🗃 التخزين\n\n"
        "قاعدة البيانات تعمل.",
        reply_markup=main_menu(),
    )

    await callback.answer()


@router.callback_query(F.data == "protection")
async def protection_callback(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "🛡 الحماية\n\n"
        "وحدة الحماية سيتم ربطها لاحقًا.",
        reply_markup=main_menu(),
    )

    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "🧠 أهلاً بك في Special\n\n"
        "لوحة التحكم الرئيسية:",
        reply_markup=main_menu(),
    )

    await callback.answer()
