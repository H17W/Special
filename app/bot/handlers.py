from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from .keyboards import main_menu


router = Router()


@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "🧠 أهلاً بك في Special\n\n"
        "لوحة التحكم الرئيسية:",
        reply_markup=main_menu(),
    )
