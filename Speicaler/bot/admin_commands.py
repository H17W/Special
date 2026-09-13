from __future__ import annotations
import time, re
from aiogram import Router, F
from aiogram.types import Message
from app.core.config import settings
from app.core.database import db
from app.core.permissions import is_owner
router=Router()

@router.message(F.text.regexp(r'^قفل الخاص$'))
async def lock_private(m):
    if is_owner(m.from_user.id): db.set_setting('private_lock','1'); await m.answer('تم قفل الخاص')
@router.message(F.text.regexp(r'^فتح الخاص$'))
async def unlock_private(m):
    if is_owner(m.from_user.id): db.set_setting('private_lock','0'); await m.answer('تم فتح الخاص')
@router.message(F.text.regexp(r'^قفل الشتم$'))
async def lock_bad(m):
    if is_owner(m.from_user.id): db.set_setting('profanity_filter','1'); await m.answer('تم تفعيل فلتر الشتم')
@router.message(F.text.regexp(r'^فتح الشتم$'))
async def unlock_bad(m):
    if is_owner(m.from_user.id): db.set_setting('profanity_filter','0'); await m.answer('تم إيقاف فلتر الشتم')
@router.message(F.text.startswith('تقييد البوت'))
async def restrict(m):
    if not is_owner(m.from_user.id):return
    parts=m.text.split(); target=None; seconds=300
    if m.reply_to_message and m.reply_to_message.from_user: target=m.reply_to_message.from_user.id; seconds=int(parts[2]) if len(parts)>2 else 300
    elif len(parts)>=2:
        raw=parts[1]
        try: target=int(re.sub(r'[^0-9-]','',raw))
        except Exception: target=(await m.bot.get_chat(raw.lstrip('@'))).id
        seconds=int(parts[2]) if len(parts)>2 else 300
    if target is None:return await m.answer('الصيغة: تقييد البوت <id> <ثواني>')
    db.restrict(target,seconds,reason='Developer restriction'); await m.answer(f'تم تقييد {target} لمدة {seconds} ثانية')
@router.message(F.text.startswith('فك تقييد البوت'))
async def unrestrict(m):
    if not is_owner(m.from_user.id):return
    parts=m.text.split(); target=int(parts[1]); db.run('DELETE FROM restrictions WHERE user_id=?',(target,)); await m.answer('تم فك التقييد')
@router.message(F.text.startswith('رابط مؤقت'))
async def temp_link(m):
    if not is_owner(m.from_user.id):return
    parts=m.text.split();
    if len(parts)<3:return await m.answer('الصيغة: رابط مؤقت <id> <ثواني>')
    target=int(parts[1]); seconds=max(60,int(parts[2])); token=db.create_link(target,seconds,grant_seconds=seconds); me=await m.bot.get_me(); await m.answer(f'https://t.me/{me.username}?start={token}\nينتهي خلال {seconds} ثانية')
@router.message(F.text.startswith('الوقت المتبقي'))
async def remaining(m):
    if not is_owner(m.from_user.id):return
    parts=m.text.split(); target=int(parts[1]) if len(parts)>1 else (m.reply_to_message.from_user.id if m.reply_to_message and m.reply_to_message.from_user else 0)
    r=db.user(target)
    if not r:return await m.answer('المستخدم غير موجود')
    if r['expires_at'] is None: return await m.answer('صلاحية دائمة')
    await m.answer(f'المتبقي: {max(0,r["expires_at"]-int(time.time()))} ثانية')

@router.message(F.text=='تقليد')
async def mimic_cmd(m):
    if not is_owner(m.from_user.id): return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        return await m.answer('❌ استخدم تقليد بالرد على رسالة الشخص')
    target_user=m.reply_to_message.from_user
    target=(f'@{target_user.username}' if getattr(target_user,'username',None) else target_user.id)
    try:
        await __import__('app.user.client',fromlist=['manager']).manager.mimic(target)
        await m.answer('🎭 تم تفعيل التقليد')
    except Exception as e:
        await m.answer(f'❌ تعذر تفعيل التقليد\n{e}')

@router.message(F.text=='الغاء التقليد')
async def restore_mimic(m):
    if not is_owner(m.from_user.id): return
    try:
        ok=await __import__('app.user.client',fromlist=['manager']).manager.restore_mimic()
        await m.answer('↩️ تم الغاء التقليد واسترجاع حسابك' if ok else 'ℹ️ لا توجد جلسة تقليد فعالة')
    except Exception as e:
        await m.answer(f'❌ تعذر الغاء التقليد\n{e}')

@router.message(F.text.startswith('استثناء الخاص'))
async def private_exception(m):
    if not is_owner(m.from_user.id): return
    target=(m.reply_to_message.from_user.id if m.reply_to_message and m.reply_to_message.from_user else (int(m.text.split()[1]) if len(m.text.split())>1 else 0))
    if not target:return await m.answer('الصيغة: استثناء الخاص <id> أو بالرد')
    db.add_private_exception(settings.owner_id,target); await m.answer('تمت إضافة الاستثناء')
@router.message(F.text.startswith('حذف استثناء الخاص'))
async def private_exception_del(m):
    if not is_owner(m.from_user.id): return
    target=int(m.text.split()[1]); db.del_private_exception(settings.owner_id,target); await m.answer('تم حذف الاستثناء')
