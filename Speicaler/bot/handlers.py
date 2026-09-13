from __future__ import annotations
import asyncio, time
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, MessageOriginUser, MessageOriginChat, MessageOriginChannel
from app.core.config import settings
from app.core.database import db
from app.core.permissions import allowed,is_owner
from app.core.ai import ask,AIError
from app.core.music import search_tracks
from app.core.audio import to_voice,AudioError
from app.user.client import manager
from .keyboards import *
from .context import session,clear

router=Router()

async def safe_send(message,text,reply_markup=None):
    # Telegram text hard limit is 4096; keep a safety margin.
    chunks=[text[i:i+3900] for i in range(0,len(text),3900)] or ['']
    for i,ch in enumerate(chunks): await message.answer(ch,reply_markup=reply_markup if i==len(chunks)-1 else None)

def identity(m): return m.from_user.id if m.from_user else 0

def abusive_start(uid):
    now=int(time.time()); r=db.one('SELECT * FROM start_abuse WHERE user_id=?',(uid,))
    if not r:
        db.run('INSERT INTO start_abuse(user_id,attempts,last_at,notify_at) VALUES(?,?,?,?)',(uid,0,now,0)); return 0
    # Reset the sequence after 24h of quiet time.
    if now-r['last_at']>86400:
        db.run('UPDATE start_abuse SET attempts=0,last_at=? WHERE user_id=?',(now,uid)); return 0
    attempts=r['attempts']+1; db.run('UPDATE start_abuse SET attempts=?,last_at=? WHERE user_id=?',(attempts,now,uid))
    # First repeated /start => 1m, second => 5m, third => 10m, fourth => permanent ban.
    if attempts==1:return 60
    if attempts==2:return 300
    if attempts==3:return 600
    return -1

@router.callback_query(F.data=='access_request')
async def access_req(c:CallbackQuery):
    uid=identity(c.message); db.upsert_user(uid,c.from_user.username,c.from_user.first_name)
    if db.access_active(uid): await c.answer('أنت مصرح لك بالفعل',show_alert=True); return
    db.request_access(uid); await c.message.edit_text('تم إرسال طلبك للمطور بنجاح');
    for r in db.pending_requests():
        if r['user_id']==uid:
            await c.bot.send_message(settings.owner_id,f'📨 طلب استخدام جديد\nالمستخدم: {uid}\nالطلب: #{r["id"]}',reply_markup=request_actions(r['id'])); break
    await c.answer()

@router.message(Command('help'))
async def help_cmd(m): await m.answer(help_text())

@router.message(F.text.in_({'الكيبورد','/keyboard'}))
async def keyboard_cmd(m):
    uid=identity(m)
    if not allowed(uid): return await m.answer('⛔ غير مصرح لك باستخدام Special.')
    sent=await m.answer('🧠 لوحة Special',reply_markup=main_menu(is_owner(uid)))
    db.run('INSERT OR REPLACE INTO keyboard_sessions(chat_id,message_id,owner_id,created_at) VALUES(?,?,?,?)',(m.chat.id,sent.message_id,uid,int(time.time())))

@router.message(F.text.regexp(r'^كتم$'))
async def mute_reply(m):
    if not allowed(identity(m),'mute'):return
    if not m.reply_to_message:return await m.answer('رد على رسالة الشخص ثم اكتب كتم')
    target=m.reply_to_message.from_user
    if not target:return await m.answer('تعذر تحديد المستخدم')
    await manager.mute(target.id); await m.answer('تم كتم هذا الشخص')

@router.message(F.text.regexp(r'^الغاء الكتم$'))
async def unmute_reply(m):
    if not allowed(identity(m),'mute'):return
    if not m.reply_to_message:return await m.answer('رد على رسالة الشخص ثم اكتب الغاء الكتم')
    target=m.reply_to_message.from_user
    if target: await manager.unmute(target.id); await m.answer('تم الغاء الكتم عن هذا المستخدم')

@router.message(F.text.regexp(r'^بداية الحذف$'))
async def delete_start_reply(m):
    if not allowed(identity(m),'delete'):return
    if not m.reply_to_message:return await m.answer('رد على الرسالة الأولى ثم اكتب بداية الحذف')
    r=m.reply_to_message; db.set_delete_start(identity(m),m.chat.id,r.message_id); await m.answer('تم حفظ بداية الحذف')

@router.message(F.text.regexp(r'^نهاية الحذف$'))
async def delete_end_reply(m):
    if not allowed(identity(m),'delete'):return
    if not m.reply_to_message:return await m.answer('رد على الرسالة الأخيرة ثم اكتب نهاية الحذف')
    st=db.delete_session(identity(m))
    if not st:return await m.answer('حدد بداية الحذف أولاً')
    if st['target_chat_id']!=m.chat.id:return await m.answer('نهاية الحذف يجب أن تكون في نفس المحادثة')
    if not await manager.can_delete(m.chat.id):return await m.answer('⛔ لا أملك صلاحية حذف الرسائل هنا')
    n=await manager.delete_range(m.chat.id,st['start_message_id'],m.reply_to_message.message_id); db.clear_delete(identity(m)); await m.answer(f'تم حذف {n} رسالة')

@router.message(F.audio)
async def audio_received(m):
    if not allowed(identity(m),'audio'):return
    from pathlib import Path
    audio_dir=Path('storage/audio'); audio_dir.mkdir(parents=True,exist_ok=True)
    path=await m.download(destination=audio_dir)
    session(identity(m)).mode='audio'; session(identity(m)).data={'path':str(path),'title':m.audio.title or '', 'artist':m.audio.performer or ''}
    await m.answer('اختر العملية:',reply_markup=audio_actions())

@router.message(F.text)
async def text_fallback(m):
    uid=identity(m)
    s=session(uid)
    if s.mode=='ai_wait':
        try: ans=await ask(m.text); await safe_send(m,ans)
        except AIError as e: await m.answer(f'❌ AI: {e}')
        finally: clear(uid)
        return
    if s.mode=='music_wait':
        try:
            tracks=await search_tracks(m.text)
            if not tracks:return await m.answer('ما لقيت نتائج موسيقية')
            await safe_send(m,'\n'.join(f'{i+1}. {x["title"]} — {x["artist"]}\n{x["url"]}' for i,x in enumerate(tracks)))
        except Exception as e: await m.answer(f'❌ خطأ البحث: {e}')
        finally: clear(uid)
        return
    if s.mode=='audio_edit':
        parts=[x.strip() for x in m.text.split('|',1)]; s.data['title']=parts[0]; s.data['artist']=parts[1] if len(parts)>1 else ''; s.mode='audio'; await m.answer('تم تحديث البيانات',reply_markup=audio_actions()); return
    if m.text.startswith('/ai '):
        try: await safe_send(m,await ask(m.text[4:]))
        except AIError as e: await m.answer(f'❌ AI: {e}')
    elif m.text.startswith('/music '):
        s.mode='music_wait'; m.text # keep lint quiet
        tracks=await search_tracks(m.text[7:]); await safe_send(m,'\n'.join(f'{i+1}. {x["title"]} — {x["artist"]}\n{x["url"]}' for i,x in enumerate(tracks)) or 'لا توجد نتائج')


@router.message(Command('حذف'))
async def delete_button(m:Message):
    if not allowed(identity(m),'delete'): return
    if not await manager.start(): return await m.answer('⚠️ حساب Telegram غير مسجل. استخدم /login')
    dialogs=[]
    async for d in manager.client.iter_dialogs(limit=30):
        if d.is_user and not getattr(d.entity,'bot',False): dialogs.append(d)
    if not dialogs:return await m.answer('لا توجد محادثات خاصة متاحة')
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b=InlineKeyboardBuilder()
    for d in dialogs[:20]: b.button(text=(d.name or str(d.id))[:35],callback_data=f'delchat:{d.id}')
    b.adjust(1); await m.answer('🗑 اختر المحادثة الخاصة التي تريد حذف نطاق رسائل منها ثم أرسل أول رسالة كـ Forward وبعدها الثانية',reply_markup=b.as_markup())

@router.message(F.forward_origin)
async def forwarded_delete_marker(m:Message):
    uid=identity(m)
    if not allowed(uid,'delete'): return
    origin=m.forward_origin
    chat_id=None; msg_id=getattr(origin,'message_id',None)
    if isinstance(origin,MessageOriginUser): chat_id=origin.sender_user.id
    elif isinstance(origin,(MessageOriginChat,MessageOriginChannel)): chat_id=origin.chat.id
    if chat_id is None or msg_id is None:return
    s=session(uid)
    if s.mode!='forward_delete': return
    if s.data.get('target')!=chat_id:return await m.answer('❌ الرسالة المرسلة ليست من المحادثة المختارة')
    if 'start' not in s.data:
        s.data['start']=msg_id; await m.answer('تم حفظ الرسالة الأولى الآن أرسل Forward للرسالة الأخيرة'); return
    if not await manager.can_delete(chat_id): return await m.answer('⛔ لا أملك صلاحية الحذف في هذه المحادثة')
    n=await manager.delete_range(chat_id,s.data['start'],msg_id); clear(uid); await m.answer(f'✅ تم حذف {n} رسالة من النطاق')

def help_text():
    return '''📖 دليل Special\n\n/start — تشغيل اللوحة\n/ai نص — سؤال للذكاء الاصطناعي\n/music اسم الأغنية — البحث عن أغنية\n/keyboard أو الكيبورد — فتح لوحة Special\n\nكتم — بالرد على رسالة الشخص\nالغاء الكتم — بالرد على رسالته\nبداية الحذف — بالرد على أول رسالة\nنهاية الحذف — بالرد على آخر رسالة\n\nفي المجموعات والقنوات تحتاج صلاحية حذف الرسائل حسب صلاحيات Telegram\nأوامر المطور الإدارية لا تعمل إلا للمالك'''
