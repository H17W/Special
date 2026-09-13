from __future__ import annotations
import time, os
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from app.core.config import settings
from app.core.database import db
from app.core.permissions import is_owner,allowed
from app.core.exporter import export_backup
from app.core.audio import to_voice,AudioError
from .keyboards import main_menu,admin_menu,request_actions
from .context import session

router=Router()

from aiogram import BaseMiddleware

class KeyboardSecurityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        msg=getattr(event,'message',None); user=getattr(event,'from_user',None)
        if msg and user:
            row=db.one('SELECT owner_id FROM keyboard_sessions WHERE chat_id=? AND message_id=?',(msg.chat.id,msg.message_id))
            if row and user.id not in (row['owner_id'],settings.owner_id):
                n=db.add_keyboard_abuse(user.id)
                if n>=3:
                    db.restrict(user.id,300,reason='Unauthorized keyboard interaction')
                    await answer(event,'⛔ تم تقييد استخدام Special لمدة 5 دقائق',True)
                else: await answer(event,'⛔ هذه اللوحة ليست لك',True)
                return
        return await handler(event,data)

router.callback_query.middleware(KeyboardSecurityMiddleware())

def uid(c): return c.from_user.id
async def answer(c,text,alert=False):
    try: await c.answer(text,show_alert=alert)
    except Exception: pass

@router.callback_query(F.data=='account')
async def account(c):
    await c.message.edit_text('👤 إدارة الحساب\n\nلتسجيل حساب Telegram استخدم /login ثم اتبع الخطوات.',reply_markup=main_menu(is_owner(uid(c)))); await answer(c)
@router.callback_query(F.data=='delete_menu')
async def delete_menu(c): await c.message.edit_text('🗑 حذف الرسائل\n\nفي أي محادثة رد على الرسالة الأولى واكتب بداية الحذف ثم رد على الأخيرة واكتب نهاية الحذف.',reply_markup=main_menu(is_owner(uid(c)))); await answer(c)
@router.callback_query(F.data=='mute_menu')
async def mute_menu(c): await c.message.edit_text('🔇 الكتم\n\nرد على رسالة الشخص واكتب كتم\nأو استخدم أوامر المطور من لوحة Special.',reply_markup=main_menu(is_owner(uid(c)))); await answer(c)
@router.callback_query(F.data=='private_menu')
async def private_menu(c):
    if not allowed(uid(c),'private_lock'): return await answer(c,'🚫 هذه الميزة غير متاحة لك',True)
    on=db.get_setting('private_lock','0')=='1'; filt=db.get_setting('profanity_filter','0')=='1'
    text=f'🔒 حماية الخاص\n\nقفل الخاص: {"مفعل" if on else "متوقف"}\nفلتر الشتم: {"مفعل" if filt else "متوقف"}\n\nاستخدم الأوامر:\nقفل الخاص\nفتح الخاص\nقفل الشتم\nفتح الشتم'
    await c.message.edit_text(text,reply_markup=main_menu(is_owner(uid(c)))); await answer(c)
@router.callback_query(F.data=='ai')
async def ai(c):
    if not allowed(uid(c),'ai'):return await answer(c,'🚫 غير متاح',True)
    session(uid(c)).mode='ai_wait'; await c.message.edit_text('🤖 اكتب سؤالك الآن وسأرسله إلى Gemini',reply_markup=main_menu(is_owner(uid(c)))); await answer(c)
@router.callback_query(F.data=='music')
async def music(c):
    if not allowed(uid(c),'music'):return await answer(c,'🚫 غير متاح',True)
    session(uid(c)).mode='music_wait'; await c.message.edit_text('🎵 اكتب اسم الأغنية أو الفنان',reply_markup=main_menu(is_owner(uid(c)))); await answer(c)
@router.callback_query(F.data=='audio_help')
async def audio_help(c): await c.message.edit_text('🎙️ أرسل ملف صوتي للبوت\n\nبعدها تقدر تحويله إلى Voice وتعديل الاسم والفنان.',reply_markup=main_menu(is_owner(uid(c)))); await answer(c)
@router.callback_query(F.data=='stats')
async def stats(c):
    s=db.stats(); text='📊 إحصائيات Special\n\n'+'\n'.join(f'{k}: {v}' for k,v in s.items()); await c.message.edit_text(text,reply_markup=main_menu(is_owner(uid(c)))); await answer(c)
@router.callback_query(F.data=='help')
async def help_cb(c):
    from .handlers import help_text
    await c.message.edit_text(help_text(),reply_markup=main_menu(is_owner(uid(c)))); await answer(c)
@router.callback_query(F.data=='admin')
async def admin(c):
    if not is_owner(uid(c)):return await answer(c,'⛔ للمالك فقط',True)
    await c.message.edit_text('🛡️ لوحة المطور',reply_markup=admin_menu()); await answer(c)
@router.callback_query(F.data=='admin_requests')
async def requests(c):
    if not is_owner(uid(c)):return await answer(c,'⛔',True)
    rows=db.pending_requests()
    if not rows:return await answer(c,'لا توجد طلبات معلقة',True)
    r=rows[0]; await c.message.edit_text(f'📨 الطلب #{r["id"]}\nالمستخدم: {r["user_id"]}',reply_markup=request_actions(r['id'])); await answer(c)
@router.callback_query(F.data.startswith('req:'))
async def decide(c):
    if not is_owner(uid(c)):return await answer(c,'⛔',True)
    parts=c.data.split(':'); action=parts[1]; rid=int(parts[2]); row=db.one('SELECT * FROM access_requests WHERE id=?',(rid,))
    if not row or row['status']!='pending':return await answer(c,'الطلب غير متاح',True)
    target=row['user_id']
    if action=='accept':
        seconds=int(parts[3]); expires=None if seconds==0 else int(time.time())+seconds; db.decide_request(rid,target,True,expires)
        await c.bot.send_message(target,'تم قبول طلبك'); await c.message.edit_text(f'✅ تم قبول الطلب #{rid}')
    else:
        db.decide_request(rid,target,False,reason='تم رفض الطلب من المطور'); await c.bot.send_message(target,'تم رفض طلبك\nالسبب: تم رفض الطلب من المطور'); await c.message.edit_text(f'❌ تم رفض الطلب #{rid}')
    await answer(c)
@router.callback_query(F.data=='admin_time')
async def admin_time(c):
    if not is_owner(uid(c)):return await answer(c,'⛔',True)
    await c.message.edit_text('⏱️ أرسل رقم المستخدم كرسالة في الخاص وسأعرض حالته.',reply_markup=admin_menu()); await answer(c)
@router.callback_query(F.data=='admin_restrict')
async def admin_restrict(c):
    if not is_owner(uid(c)):return await answer(c,'⛔',True)
    await c.message.edit_text('🚫 أرسل: تقييد البوت <id> <ثواني>\nأو رد على رسالة مستخدم واكتب تقييد البوت 300',reply_markup=admin_menu()); await answer(c)
@router.callback_query(F.data=='admin_link')
async def admin_link(c):
    if not is_owner(uid(c)):return await answer(c,'⛔',True)
    await c.message.edit_text('🔗 أرسل: رابط مؤقت <id> <ثواني>'); await answer(c)
@router.callback_query(F.data=='backup')
async def backup(c):
    if not is_owner(uid(c)):return await answer(c,'⛔',True)
    p=export_backup(); await c.message.answer_document(__import__('aiogram').types.FSInputFile(str(p))); await answer(c)
@router.callback_query(F.data.startswith('audio:'))
async def audio_cb(c):
    if not allowed(uid(c),'audio'):return await answer(c,'🚫 غير متاح',True)
    s=session(uid(c))
    if not s.data:return await answer(c,'جلسة الصوت انتهت',True)
    if c.data=='audio:edit': s.mode='audio_edit'; await c.message.edit_text('✏️ أرسل بالشكل:\nاسم الأغنية | اسم الفنان'); return await answer(c)
    try:
        src=s.data['path']; dst=src.rsplit('.',1)[0]+'.ogg'; await to_voice(__import__('pathlib').Path(src),__import__('pathlib').Path(dst))
        await c.message.answer_voice(__import__('aiogram').types.FSInputFile(dst),caption=f'{s.data.get("title","")} — {s.data.get("artist","")}')
        await answer(c,'تم التحويل')
    except AudioError as e: await answer(c,str(e),True)

@router.callback_query(F.data.startswith('delchat:'))
async def choose_delete_chat(c):
    from .context import session
    if not allowed(uid(c),'delete'): return await answer(c,'🚫 غير متاح',True)
    target=int(c.data.split(':',1)[1]); s=session(uid(c)); s.mode='forward_delete'; s.data={'target':target}
    await c.message.edit_text('📥 أرسل الآن Forward للرسالة الأولى من المحادثة المختارة\nثم Forward للرسالة الأخيرة')
    await answer(c)
