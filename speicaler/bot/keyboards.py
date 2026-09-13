from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def access_request(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📨 إرسال طلب استخدام للمطور',callback_data='access_request')]])
def main_menu(owner=False):
    b=InlineKeyboardBuilder()
    b.button(text='👤 إدارة الحساب',callback_data='account')
    b.button(text='🗑 حذف الرسائل',callback_data='delete_menu')
    b.button(text='🔇 الكتم',callback_data='mute_menu')
    b.button(text='🔒 حماية الخاص',callback_data='private_menu')
    b.button(text='🤖 الذكاء الاصطناعي',callback_data='ai')
    b.button(text='🎵 البحث عن أغنية',callback_data='music')
    b.button(text='🎙️ تحويل صوت إلى فويس',callback_data='audio_help')
    b.button(text='📊 الإحصائيات',callback_data='stats')
    b.button(text='📖 دليل الأوامر',callback_data='help')
    if owner:
        b.button(text='🛡️ لوحة المطور',callback_data='admin')
    b.adjust(2)
    return b.as_markup()

def admin_menu():
    b=InlineKeyboardBuilder(); b.button(text='📨 طلبات الوصول',callback_data='admin_requests'); b.button(text='⏱️ الوقت المتبقي',callback_data='admin_time'); b.button(text='🚫 تقييد مستخدم',callback_data='admin_restrict'); b.button(text='🔗 رابط مؤقت',callback_data='admin_link'); b.button(text='📈 إحصائيات',callback_data='stats'); b.button(text='💾 نسخة احتياطية',callback_data='backup'); b.adjust(2); return b.as_markup()

def request_actions(rid):
    b=InlineKeyboardBuilder(); b.button(text='✅ قبول دائم',callback_data=f'req:accept:{rid}:0'); b.button(text='⏱️ قبول 24 ساعة',callback_data=f'req:accept:{rid}:86400'); b.button(text='⏱️ قبول 7 أيام',callback_data=f'req:accept:{rid}:604800'); b.button(text='❌ رفض',callback_data=f'req:reject:{rid}'); b.adjust(2); return b.as_markup()

def audio_actions(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🎙️ تحويل إلى فويس',callback_data='audio:voice')],[InlineKeyboardButton(text='✏️ تعديل الاسم والفنان',callback_data='audio:edit')]])

def keyboard_reply(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='الكيبورد')],[KeyboardButton(text='🧠 Special')]],resize_keyboard=True)
