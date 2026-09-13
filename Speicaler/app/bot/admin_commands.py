import time
from aiogram import Router,F
from aiogram.filters import Command
from aiogram.types import Message
from app.core.config import settings
from app.core.database import db
from app.core.permissions import is_owner
from app.services.broadcast import run_broadcast
router=Router()
@router.message(Command('broadcast'))
async def broadcast(m:Message):
 if not is_owner(m.from_user.id):return
 text=(m.text or '').split(maxsplit=1); text=text[1] if len(text)>1 else ''
 if not text:return await m.answer('استخدم /broadcast نص الرسالة')
 rows=db.all("SELECT id FROM users WHERE status='active'"); targets=[int(r['id']) for r in rows]; cur=db.one('SELECT COALESCE(MAX(id),0)+1 x FROM broadcast_jobs'); jid=int(cur['x']); db.run('INSERT INTO broadcast_jobs(id,owner_id,status,created_at,total,sent,failed,text) VALUES(?,?,?,?,?,?,?,?)',(jid,m.from_user.id,'queued',int(time.time()),len(targets),0,0,text)); await m.answer(f'📢 بدأت الإذاعة إلى {len(targets)} مستخدم'); sent,failed=await run_broadcast(m.bot,text,targets,jid); await m.answer(f'📊 انتهت الإذاعة\nنجح: {sent}\nفشل: {failed}')
@router.message(Command('importprivate'))
async def importprivate(m:Message):
 if not is_owner(m.from_user.id):return
 await m.answer('استخدم زر استيراد الخاص أو أرسل ID المحادثة بعد فتحه')
@router.message(Command('login'))
async def login(m:Message):
 if not is_owner(m.from_user.id):return
 await m.answer('تسجيل الدخول لحساب Telegram يتم عبر مسار تسجيل الدخول المخصص في النظام حفاظاً على الجلسة وعدم تخزين رمز الدخول في قاعدة البيانات.')
