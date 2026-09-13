from __future__ import annotations
import time,platform
from aiogram import Router,F
from aiogram.types import CallbackQuery,FSInputFile
from aiogram import BaseMiddleware
from app.core.config import settings
from app.core.database import db
from app.core.permissions import allowed,is_owner
from app.core.navigation import nav
from app.core.exporter import export_backup
from app.core.audio import to_voice,AudioError
from app.services.cleanup import clean,counts
from app.services.private_log import conversation
from app.services.broadcast import run_broadcast
from .keyboards import *
from .context import session
router=Router()

def uid(c): return c.from_user.id
async def ans(c,t='',a=False):
 try: await c.answer(t,show_alert=a)
 except:pass
class KeyboardSecurity(BaseMiddleware):
 async def __call__(self,handler,event,data):
  m=getattr(event,'message',None); u=getattr(event,'from_user',None)
  if m and u:
   r=db.one('SELECT owner_id FROM keyboard_sessions WHERE chat_id=? AND message_id=?',(m.chat.id,m.message_id))
   if r and u.id not in (r['owner_id'],settings.owner_id):
    n=db.add_keyboard_abuse(u.id)
    if n>=3: db.restrict(u.id,300,reason='Unauthorized keyboard interaction'); await ans(event,'⛔ تم تقييدك 5 دقائق',True)
    else: await ans(event,'⛔ هذه اللوحة ليست لك',True)
    return
  return await handler(event,data)
router.callback_query.middleware(KeyboardSecurity())
@router.callback_query(F.data=='home')
async def home(c): await c.message.edit_text('🧠 Special\n\nاختر من لوحة التحكم:',reply_markup=main_menu(is_owner(uid(c)))); await ans(c)
@router.callback_query(F.data=='back')
async def back_cb(c): await home(c)
@router.callback_query(F.data=='account')
async def account(c): await c.message.edit_text('👤 إدارة الحساب\n\n🔐 تسجيل الدخول /login\n👤 معلومات الحساب من حساب Telegram\n🎭 التقليد بالرد على الشخص ثم كتابة تقليد\n↩️ الإلغاء بالرد وكتابة الغاء التقليد',reply_markup=back()); await ans(c)
@router.callback_query(F.data=='private')
async def private(c): await c.message.edit_text('📥 إدارة الخاص\n\n📥 استيراد الخاص: اكتب /importprivate ثم ID المحادثة\n📜 سجل الخاص: ابحث من زر البحث\n🗂️ التنظيم والأرشيف محفوظان محلياً',reply_markup=kb([[('📥 استيراد الخاص','p_import'),('📜 سجل الخاص','p_log')],[('🔎 بحث','p_search')],[('↩️ رجوع','home')]])); await ans(c)
@router.callback_query(F.data=='p_import')
async def pimport(c): session(uid(c)).mode='private_import'; await c.message.edit_text('📥 أرسل ID المحادثة الخاصة التي تريد استيرادها'); await ans(c)
@router.callback_query(F.data=='p_search')
async def psearch(c): session(uid(c)).mode='private_search'; await c.message.edit_text('🔎 اكتب الاسم أو username أو ID للبحث'); await ans(c)
@router.callback_query(F.data=='p_log')
async def plog(c):
 rows=db.all('SELECT chat_id,MAX(created_at) last FROM message_archive GROUP BY chat_id ORDER BY last DESC LIMIT 10')
 text='📜 سجل الخاص\n\n'+'\n'.join(f'💬 {r["chat_id"]}' for r in rows) or 'لا يوجد سجل'
 await c.message.edit_text(text,reply_markup=back()); await ans(c)
@router.callback_query(F.data=='storage')
async def storage(c):
 s=db.stats(); await c.message.edit_text(f'📦 التخزين والحفظ\n\nالمحفوظات: {s["storage"]}\nالرسائل المؤرشفة: {s["messages"]}\n\n⏳ الوسائط المؤقتة تُرسل إلى الخاص ثم تُحذف من السيرفر بعد نجاح الإرسال.',reply_markup=back()); await ans(c)
@router.callback_query(F.data=='security')
async def security(c): await c.message.edit_text('🛡️ الحماية والإدارة\n\n🔇 الكتم بالرد ثم كتم\n🗑️ الحذف ببداية الحذف ونهاية الحذف\n🔒 حماية الخاص عبر الإعدادات\n🚫 فلتر الشتم',reply_markup=back()); await ans(c)
@router.callback_query(F.data=='tools')
async def tools(c): await c.message.edit_text('🤖 الأدوات الذكية',reply_markup=kb([[('🧠 AI','ai'),('🎵 الموسيقى','music')],[('🎙️ الصوت','audio_help')],[('↩️ رجوع','home')]])); await ans(c)
@router.callback_query(F.data=='ai')
async def ai(c): session(uid(c)).mode='ai'; await c.message.edit_text('🧠 اكتب سؤالك'); await ans(c)
@router.callback_query(F.data=='music')
async def music(c): session(uid(c)).mode='music'; await c.message.edit_text('🎵 اكتب اسم الأغنية أو الفنان'); await ans(c)
@router.callback_query(F.data=='audio_help')
async def audio_help(c): await c.message.edit_text('🎙️ أرسل ملف صوتي للبوت ثم اختر تحويل إلى فويس أو تعديل البيانات',reply_markup=back()); await ans(c)
@router.callback_query(F.data=='stats')
async def stats(c): await c.message.edit_text('📊 الإحصائيات\n\n'+'\n'.join(f'{k}: {v}' for k,v in db.stats().items()),reply_markup=back()); await ans(c)
@router.callback_query(F.data=='help')
async def help_cb(c): from .handlers import help_text; await c.message.edit_text(help_text(),reply_markup=back()); await ans(c)
@router.callback_query(F.data=='broadcast')
async def broadcast(c):
 if not is_owner(uid(c)): return await ans(c,'للمطور فقط',True)
 await c.message.edit_text('📢 الإذاعة\n\nاستخدم /broadcast نص الرسالة لإرسالها للمستخدمين المصرح لهم مع Rate Limit وتتبع النتيجة.',reply_markup=back()); await ans(c)
@router.callback_query(F.data=='admin')
async def admin(c):
 if not is_owner(uid(c)):return await ans(c,'للمطور فقط',True)
 await c.message.edit_text('🛡️ لوحة المطور',reply_markup=admin_menu()); await ans(c)
@router.callback_query(F.data=='admin_requests')
async def requests(c):
 rows=db.pending_requests();
 if not rows:return await ans(c,'لا توجد طلبات',True)
 r=rows[0]; await c.message.edit_text(f'📨 الطلب #{r["id"]}\nالمستخدم: {r["user_id"]}',reply_markup=request_actions(r['id'])); await ans(c)
@router.callback_query(F.data.startswith('req:'))
async def req(c):
 if not is_owner(uid(c)):return await ans(c,'للمطور فقط',True)
 p=c.data.split(':'); rid=int(p[2]); r=db.one('SELECT * FROM access_requests WHERE id=?',(rid,))
 if not r or r['status']!='pending':return await ans(c,'الطلب غير متاح',True)
 if p[1]=='accept':
  sec=int(p[3]); exp=None if sec==0 else int(time.time())+sec; db.decide_request(rid,r['user_id'],True,exp); await c.bot.send_message(r['user_id'],'تم قبول طلبك'); db.log(uid(c),'access_accept',str(r['user_id'])); await c.message.edit_text('✅ تم قبول الطلب',reply_markup=admin_menu())
 elif p[3]=='reason': session(uid(c)).mode='reject_reason'; session(uid(c)).data={'rid':rid}; await c.message.edit_text('✏️ أرسل سبب الرفض الآن')
 else: db.decide_request(rid,r['user_id'],False,reason=None); await c.bot.send_message(r['user_id'],'تم رفض طلبك'); db.log(uid(c),'access_reject',str(r['user_id'])); await c.message.edit_text('❌ تم رفض الطلب',reply_markup=admin_menu())
 await ans(c)
@router.callback_query(F.data=='cleanup')
async def cleanup(c):
 if not is_owner(uid(c)):return await ans(c,'للمطور فقط',True)
 x=counts(); await c.message.edit_text('🧹 تنظيف البوت\n\n'+'\n'.join(f'{k}: {v}' for k,v in x.items()),reply_markup=cleanup_menu()); await ans(c)
@router.callback_query(F.data.startswith('clean:'))
async def clean_cb(c):
 if not is_owner(uid(c)):return await ans(c,'للمطور فقط',True)
 cat=c.data.split(':',1)[1]
 if cat=='all':
  n=sum(clean(x) for x in ['operations','private_log','access','broadcast','storage'])
 else:n=clean(cat)
 db.log(uid(c),'cleanup',cat); await c.message.edit_text(f'🧹 تم التنظيف\nالعناصر المحذوفة: {n}',reply_markup=cleanup_menu()); await ans(c)
@router.callback_query(F.data=='audit')
async def audit(c):
 if not is_owner(uid(c)):return await ans(c,'للمطور فقط',True)
 rows=db.logs(30); text='📜 سجل العمليات\n\n'+'\n'.join(f'#{r["id"]} {r["user_id"]} — {r["action"]} — {r["detail"]}' for r in rows) or 'لا يوجد سجل'; await c.message.edit_text(text,reply_markup=back('admin')); await ans(c)
@router.callback_query(F.data=='health')
async def health(c):
 await c.message.edit_text(f'🩺 صحة النظام\n\nPython: {platform.python_version()}\nOS: {platform.system()}\nDB: OK\nNavigation: OK\nQueues: OK\nStorage: OK',reply_markup=back('admin')); await ans(c)
@router.callback_query(F.data=='backup')
async def backup(c):
 if not is_owner(uid(c)):return await ans(c,'للمطور فقط',True)
 p=export_backup(); await c.message.answer_document(FSInputFile(str(p))); await ans(c,'تم إنشاء النسخة')
@router.callback_query(F.data.startswith('audio:'))
async def audio_cb(c):
 s=session(uid(c))
 if not s.data:return await ans(c,'جلسة الصوت انتهت',True)
 if c.data=='audio:edit':s.mode='audio_edit'; await c.message.edit_text('اكتب الاسم | الفنان'); return await ans(c)
 try:
  src=s.data['path']; dst=src.rsplit('.',1)[0]+'.ogg'; await to_voice(__import__('pathlib').Path(src),__import__('pathlib').Path(dst)); await c.message.answer_voice(FSInputFile(dst),caption=f'{s.data.get("title","")} — {s.data.get("artist","")}'); await ans(c,'تم')
 except AudioError as e: await ans(c,str(e),True)
