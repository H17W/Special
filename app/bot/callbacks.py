from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.core.config import ADMIN_ID
from app.user.moderation import muted_users

from .handlers import waiting_for_mute, waiting_for_unmute
from .keyboards import (
    main_menu,
    automation_menu,
    back_to_automation,
)


router = Router()


def is_admin(callback: CallbackQuery) -> bool:
    return (
        ADMIN_ID
        and callback.from_user
        and str(callback.from_user.id) == str(ADMIN_ID)
    )


@router.callback_query()
async def all_callbacks(callback: CallbackQuery):
    if not is_admin(callback):
        await callback.answer(
            "⛔ غير مصرح لك.",
            show_alert=True,
        )
        return

    data = callback.data

    if data == "automation":
        users = muted_users()

        await callback.message.edit_text(
            "🧠 User Automation\n\n"
            f"🔇 عدد المستخدمين المكتومين: {len(users)}",
            reply_markup=automation_menu(),
        )

        await callback.answer()
        return

    if data == "mute_user":
        waiting_for_mute.add(callback.from_user.id)

        await callback.message.edit_text(
            "🔇 كتم مستخدم\n\n"
            "أرسل Telegram ID للمستخدم الذي تريد كتمه.",
            reply_markup=back_to_automation(),
        )

        await callback.answer()
        return

    if data == "unmute_user":
        waiting_for_unmute.add(callback.from_user.id)

        await callback.message.edit_text(
            "🔊 إلغاء كتم\n\n"
            "أرسل Telegram ID للمستخدم الذي تريد إلغاء كتمه.",
            reply_markup=back_to_automation(),
        )

        await callback.answer()
        return

    if data == "muted_list":
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
        return

    if data == "main_menu":
        await callback.message.edit_text(
            "🧠 أهلاً بك في Special\n\n"
            "لوحة التحكم الرئيسية:",
            reply_markup=main_menu(),
        )

        await callback.answer()
        return

    if data == "private":
        await callback.message.edit_text(
            "📥 إدارة الخاص\n\n"
            "هذه الوحدة سيتم ربط وظائفها لاحقًا.",
            reply_markup=main_menu(),
        )

        await callback.answer()
        return

    if data == "storage":
        await callback.message.edit_text(
            "🗃 التخزين\n\n"
            "قاعدة البيانات تعمل.",
            reply_markup=main_menu(),
        )

        await callback.answer()
        return

    if data == "protection":
        await callback.message.edit_text(
            "🛡 الحماية\n\n"
            "وحدة الحماية سيتم ربطها لاحقًا.",
            reply_markup=main_menu(),
        )

        await callback.answer()
        return

    if data == "settings":
        await callback.message.edit_text(
            "⚙️ الإعدادات\n\n"
            "الإعدادات سيتم ربطها لاحقًا.",
            reply_markup=main_menu(),
        )

        await callback.answer()
        return

    await callback.answer()
