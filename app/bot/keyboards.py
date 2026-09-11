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
