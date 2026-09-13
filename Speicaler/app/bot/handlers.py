from __future__ import annotations
import time,asyncio
from aiogram import Router,F
from aiogram.filters import Command,CommandStart
from aiogram.types import Message
from app.core.config import settings
from app.core.database import db
from app.core.permissions import allowed,is_owner
from app.core.ai import ask,AIError
from app.core.music import search_tracks
from app.core.audio import to_voice,AudioError
from app.core.navigation import nav
from app.user.client import manager
from app.services.mimic import MimicService
from .keyboards import *
from .context import session,clear
router=Router(); mimic=MimicService(manager.client)

def uid(m): return m.from_user.id if m.from_user else 0
def help_text(): return '''📖 دليل Special\n\n/start تشغيل Special\n/ai نص الذكاء الاصطناعي\n/music اسم البحث عن أغنية\n/keyboard أو الكيبورد فتح لوحة Special\n\nكتم بالرد على رسالة الشخص\nالغاء الكتم بالرد عليه\nبداية الحذف بالرد على أول رسالة\nنهاية الحذف بالرد على آخر رسالة\nتقليد بالرد على الشخص\nالغاء التقليد بالرد على الشخص\n\nالميزات الإدارية تظهر للمطور فقط'''

def abusive(uid):
 now=int(time.time()); r=db.one('SELECT * FROM start_abuse WHERE user_id=?',(uid,))
 if not r: db.run('INSERT INTO start_abuse VALUES(?,?,?,?)',(uid,0,now,0)); return 0
 if now-r['last_at']>86400: db.run('UPDATE start_abuse SET attempts=0,last_at=? WHERE user_id=?',(now,uid)); return 0
 n=r['attempts']+1; db.run('UPDATE start_abuse SET attempts=?,last_at=? WHERE user_id=?',(n,now,uid)); return {-1:0,1:60,2:300,3:600}.get(n,-1)
@router.message(CommandStart())
async def start(m:Message):
 u=uid(m); db.upsert_user(u,m.from_user.username,m.from_user.first_name)
 payload=(m.text or '').split(maxsplit=1)[1] if len((m.text or '').split())>1 else ''
 if payload and not db.access_active(u):
  x=db.consume_link(payload,u)
  if x: db.run('UPDATE users SET status="active",expires_at=?,updated_at=? WHERE id=?',(int(time.time())+x[1],int(time.time()),u))
 if not is_owner(u) and not db.access_active(u):
  d=abusive(u)
  if d==-1: db.restrict(u,permanent=True,reason='Repeated /start abuse')
  elif d>0: db.restrict(u,d,reason='Repeated /start')
  db.log(u,'start','unauthorized')
  await m.answer('⛔ غير مصرح لك باستخدام Special.',reply_markup=access_request()); return
 if not db.unrestricted(u): return await m.answer('⛔ حسابك مقيّد حالياً')
 await m.answer('🧠 أهلاً بك في Special\n\nاختر من لوحة التحكم:',reply_markup=main_menu(is_owner(u)))
@router.callback_query(F.data=='access_request')
async def access_req(c):
 u=uid(c.message); rid,new=db.request_access(u); await c.message.edit_text('تم إرسال طلبك للمطور بنجاح');
 if new: await c.bot.send_message(settings.owner_id,f'📨 طلب استخدام جديد\nالمستخدم: {u}\nالطلب: #{rid}',reply_markup=request_actions(rid))
 await c.answer()
@router.message(Command('help'))
async def help_cmd(m): await m.answer(help_text())
@router.message(F.text.in_({'الكيبورد','/keyboard'}))
async def keyboard(m):
 u=uid(m)
 if not allowed(u): return await m.answer('⛔ غير مصرح لك باستخدام Special.')
 s=await m.answer('🧠 لوحة Special',reply_markup=main_menu(is_owner(u))); db.run('INSERT OR REPLACE INTO keyboard_sessions VALUES(?,?,?,?)',(m.chat.id,s.message_id,u,int(time.time())))
@router.message(F.text=='كتم')
async def mute(m):
 if not allowed(uid(m),'mute'):return
 if not m.reply_to_message or not m.reply_to_message.from_user:return await m.answer('رد على رسالة الشخص ثم اكتب كتم')
 await manager.mute(m.reply_to_message.from_user.id); await m.answer('تم كتم هذا الشخص')
@router.message(F.text=='الغاء الكتم')
async def unmute(m):
 if not allowed(uid(m),'mute'):return
 if not m.reply_to_message or not m.reply_to_message.from_user:return await m.answer('رد على رسالة الشخص ثم اكتب الغاء الكتم')
 await manager.unmute(m.reply_to_message.from_user.id); await m.answer('تم الغاء الكتم عن هذا المستخدم')
@router.message(F.text=='بداية الحذف')
async def ds(m):
 if not allowed(uid(m),'delete') or not m.reply_to_message:return
 db.set_delete_start(uid(m),m.chat.id,m.reply_to_message.message_id); await m.answer('تم حفظ بداية الحذف')
@router.message(F.text=='نهاية الحذف')
async def de(m):
 if not allowed(uid(m),'delete') or not m.reply_to_message:return
 st=db.delete_session(uid(m));
 if not st or st['target_chat_id']!=m.chat.id:return await m.answer('حدد بداية الحذف أولاً وفي نفس المحادثة')
 if not await manager.can_delete(m.chat.id):return await m.answer('⛔ لا أملك صلاحية الحذف هنا')
 n=await manager.delete_range(m.chat.id,st['start_message_id'],m.reply_to_message.message_id); db.clear_delete(uid(m)); await m.answer(f'تم حذف {n} رسالة')
@router.message(F.text=='تقليد')
async def mimic_start(m):
 if not allowed(uid(m),'mimic') or not m.reply_to_message or not m.reply_to_message.from_user:return
 try: await mimic.start(m.reply_to_message.from_user.id); await m.answer('🎭 تم تفعيل التقليد')
 except Exception as e: await m.answer(f'❌ تعذر تفعيل التقليد: {e}')
@router.message(F.text=='الغاء التقليد')
async def mimic_stop(m):
 if not allowed(uid(m),'mimic') or not m.reply_to_message:return
 try: await mimic.restore(); await m.answer('↩️ تم استرجاع بياناتك الأصلية')
 except Exception as e: await m.answer(f'❌ تعذر الاسترجاع: {e}')
@router.message(F.audio)
async def audio(m):
 if not allowed(uid(m),'audio'):return
 from pathlib import Path
 d=Path('storage/audio'); d.mkdir(parents=True,exist_ok=True); p=d/(m.audio.file_name or f'{m.message_id}.bin'); await m.bot.download(m.audio.file_id,destination=p); session(uid(m)).data={'path':str(p),'title':m.audio.title or '','artist':m.audio.performer or ''}; await m.answer('🎙️ اختر العملية',reply_markup=audio_actions())
@router.message(F.text)
async def text(m):
 s=session(uid(m))
 if s.mode=='ai':
  try: await m.answer(await ask(m.text))
  except AIError as e: await m.answer(f'❌ AI: {e}')
  clear(uid(m)); return
 if s.mode=='music':
  try:
   r=await search_tracks(m.text); await m.answer('\n'.join(f'{i+1}. {x["title"]} — {x["artist"]}\n{x["url"]}' for i,x in enumerate(r)) or 'لا توجد نتائج')
  except Exception as e: await m.answer(f'❌ {e}')
  clear(uid(m)); return
 if s.mode=='private_import':
  try: n=await manager.import_private(int(m.text.strip()),limit=1000); await m.answer(f'📥 تم استيراد {n} رسالة')
  except Exception as e: await m.answer(f'❌ تعذر الاستيراد: {e}')
  clear(uid(m)); return
 if s.mode=='private_search':
  from app.services.private_log import search_people
  rows=search_people(m.text.strip()); await m.answer('\n'.join(f'{r["chat_id"]} — {r["sender_name"]} @{r["sender_username"] or "-"}' for r in rows) or 'لا توجد نتائج'); clear(uid(m)); return
 if s.mode=='audio_edit':
  p=[x.strip() for x in m.text.split('|',1)]; s.data['title']=p[0]; s.data['artist']=p[1] if len(p)>1 else ''; s.mode='audio'; await m.answer('تم تحديث البيانات',reply_markup=audio_actions()); return
 if m.text.startswith('/ai '):
  try: await m.answer(await ask(m.text[4:]))
  except AIError as e: await m.answer(f'❌ {e}')
 elif m.text.startswith('/music '):
  try:
   r=await search_tracks(m.text[7:]); await m.answer('\n'.join(f'{i+1}. {x["title"]} — {x["artist"]}\n{x["url"]}' for i,x in enumerate(r)) or 'لا توجد نتائج')
  except Exception as e: await m.answer(f'❌ {e}')
