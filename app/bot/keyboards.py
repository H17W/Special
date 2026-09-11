from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 User Automation",
                    callback_data="automation",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📥 إدارة الخاص",
                    callback_data="private",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗃 التخزين",
                    callback_data="storage",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛡 الحماية",
                    callback_data="protection",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ الإعدادات",
                    callback_data="settings",
                )
            ],
        ]
    )


def automation_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔇 كتم مستخدم",
                    callback_data="mute_user",
                ),
                InlineKeyboardButton(
                    text="🔊 إلغاء كتم",
                    callback_data="unmute_user",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👥 المكتومون",
                    callback_data="muted_list",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 رجوع",
                    callback_data="main_menu",
                )
            ],
        ]
    )


def private_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔇 إدارة الكتم",
                    callback_data="automation",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 رجوع",
                    callback_data="main_menu",
                )
            ],
        ]
    )


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔇 إعدادات الكتم",
                    callback_data="automation",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 رجوع",
                    callback_data="main_menu",
                )
            ],
        ]
    )


def back_to_automation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 User Automation",
                    callback_data="automation",
                )
            ]
        ]
    )
