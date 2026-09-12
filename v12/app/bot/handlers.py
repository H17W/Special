from aiogram import Router, F
from aiogram.types import Message
from app.core.config import ADMIN_ID
from app.core.database import init_database,get_allowed_user,get_feature_permissions
from app.user.moderation import mute,unmute
from .keyboards import main_menu,automation_menu,broadcast_menu,access_menu

router=Router(); waiting_for_mute=set(); waiting_for_unmute=set(); pending={}

def is_admin(message): return bool(ADMIN_ID and message.from_user and str(message.from_user.id)==str(ADMIN_ID))
def access_ok(user_id):
    if ADMIN_ID and str(user_id)==str(ADMIN_ID): return True
    r=get_allowed_user(user_id)
    return bool(r and r["status"]=="active")
def menu_for(uid): return main_menu(None) if (ADMIN_ID and str(uid)==str(ADMIN_ID)) else main_menu(uid,get_feature_permissions(uid))

@router.message(F.text.regexp(r"^/start(?:@\w+)?$"))
async def start_handler(message:Message):
    init_database(); uid=message.from_user.id if message.from_user else 0
    print(f"📩 /start وصل من {uid}")
    if not access_ok(uid): await message.answer("⛔ غير مصرح لك باستخدام Special."); return
    await message.answer("🧠 أهلاً بك في Special\n\nلوحة التحكم الرئيسية:",reply_markup=menu_for(uid))

@router.message()
async def text_handler(message:Message):
    uid=message.from_user.id if message.from_user else 0
    if not access_ok(uid): return
    if uid in waiting_for_mute:
        waiting_for_mute.discard(uid)
        try: target=int((message.text or '').strip())
        except ValueError: await message.answer('❌ أرسل Telegram ID رقمي فقط.'); return
        mute(target); await message.answer(f'🔇 تم كتم المستخدم بنجاح\n\nID: {target}',reply_markup=automation_menu()); return
    if uid in waiting_for_unmute:
        waiting_for_unmute.discard(uid)
        try: target=int((message.text or '').strip())
        except ValueError: await message.answer('❌ أرسل Telegram ID رقمي فقط.'); return
        ok=unmute(target); await message.answer(('🔊 تم إلغاء الكتم عن المستخدم بنجاح.' if ok else 'ℹ️ المستخدم غير موجود في قائمة المكتومين.')+f'\n\nID: {target}',reply_markup=automation_menu()); return
    state=pending.get(uid)
    if not state:return
    action=state.get('action')
    if action=='broadcast_text':
        pending[uid]={'action':'broadcast_confirm','text':message.text or ''}
        from .keyboards import broadcast_confirm_menu
        await message.answer(f"📢 معاينة الإذاعة\n\n{message.text or '[رسالة بدون نص]'}\n\nهل تريد إرسالها الآن؟",reply_markup=broadcast_confirm_menu()); return
    if action=='broadcast_exclude':
        pending.pop(uid,None)
        try: target=int((message.text or '').strip())
        except ValueError: await message.answer('❌ أرسل ID رقميًا.',reply_markup=broadcast_menu()); return
        from app.core.database import set_broadcast_exclusion
        set_broadcast_exclusion(target); await message.answer('🚫 تم استثناءه من الإذاعة',reply_markup=broadcast_menu()); return
    if action=='access_add':
        pending.pop(uid,None)
        try: target=int((message.text or '').strip())
        except ValueError: await message.answer('❌ أرسل Telegram ID رقمي فقط.',reply_markup=access_menu()); return
        if str(target)==str(ADMIN_ID): await message.answer('ℹ️ هذا هو المالك أصلًا.',reply_markup=access_menu()); return
        from app.core.database import add_allowed_user,ensure_feature_permissions
        add_allowed_user(target,None,str(target),None); ensure_feature_permissions(target)
        await message.answer('✅ تم السماح للمستخدم باستخدام Special\n\n🛠️ كل صلاحية متاحة له ويمكنك التحكم في كل ميزة بشكل مستقل من لوحة المطور.',reply_markup=access_menu()); return
    if action=='access_remove':
        pending.pop(uid,None)
        try: target=int((message.text or '').strip())
        except ValueError: await message.answer('❌ أرسل Telegram ID رقمي فقط.',reply_markup=access_menu()); return
        from app.core.database import remove_allowed_user
        remove_allowed_user(target); await message.answer('🗑️ تمت إزالة صلاحية المستخدم.',reply_markup=access_menu())
