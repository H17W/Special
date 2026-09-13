from __future__ import annotations
import re,time,asyncio
from pathlib import Path
from telethon import TelegramClient,events,functions
from telethon.errors import SessionPasswordNeededError
from app.core.config import settings,STORAGE
from app.core.database import db
from app.core.logger import log
from app.services.private_log import save_message

class UserAutomation:
 def __init__(self):
  self.client=TelegramClient(str(STORAGE/settings.session_name),settings.api_id,settings.api_hash); self.login_phone=None; self.login_hash=None; self.owner_id=settings.owner_id; self.mimic_lock=asyncio.Lock(); self._events()
 def _events(self):
  @self.client.on(events.NewMessage(incoming=True))
  async def i(e): await self.on_incoming(e)
  @self.client.on(events.NewMessage(outgoing=True))
  async def o(e): await self.on_outgoing(e)
  @self.client.on(events.MessageEdited())
  async def ed(e): await self.on_edited(e)
  @self.client.on(events.MessageDeleted())
  async def de(e): await self.on_deleted(e)
 async def start(self):
  await self.client.connect()
  if not await self.client.is_user_authorized(): return False
  me=await self.client.get_me()
  if me.id!=settings.owner_id: await self.client.disconnect(); raise RuntimeError('جلسة Telegram لا تطابق OWNER_ID')
  self.owner_id=me.id; return True
 async def stop(self): await self.client.disconnect()
 async def send_code(self,phone):
  r=await self.client.send_code_request(phone); self.login_phone=phone; self.login_hash=r.phone_code_hash
 async def sign_in_code(self,code):
  try: await self.client.sign_in(self.login_phone,code,phone_code_hash=self.login_hash)
  except SessionPasswordNeededError:return 'PASSWORD_REQUIRED'
  return await self._check_login()
 async def sign_in_password(self,password): await self.client.sign_in(password=password); return await self._check_login()
 async def _check_login(self):
  me=await self.client.get_me()
  if me.id!=settings.owner_id: await self.client.log_out(); raise RuntimeError('الحساب المسجل لا يطابق OWNER_ID')
  self.login_phone=self.login_hash=None; return 'OK'
 async def resolve(self,target):
  if isinstance(target,int) or (isinstance(target,str) and target.lstrip('-').isdigit()): return await self.client.get_entity(int(target))
  return await self.client.get_entity(target)
 async def mute(self,target): ent=await self.resolve(target); db.mute(ent.id,getattr(ent,'username','') or ''); db.log(self.owner_id,'mute',str(ent.id)); return ent
 async def unmute(self,target): ent=await self.resolve(target); db.unmute(ent.id); db.log(self.owner_id,'unmute',str(ent.id)); return ent
 async def can_delete(self,chat_id):
  ent=await self.resolve(chat_id)
  if getattr(ent,'broadcast',False) or getattr(ent,'megagroup',False):
   p=await self.client.get_permissions(ent,await self.client.get_me()); return bool(getattr(p,'delete_messages',False) or getattr(p,'is_creator',False))
  return True
 async def delete_range(self,chat_id,start,end):
  ent=await self.resolve(chat_id); start,end=sorted((int(start),int(end))); total=0
  for x in range(start,end+1,100):
   ids=list(range(x,min(end,x+99)+1));
   try: r=await self.client.delete_messages(ent,ids); total+=len(r) if r is not None else len(ids)
   except Exception as e: log.warning('delete batch: %s',e)
  db.log(self.owner_id,'delete',f'{chat_id}:{start}-{end}:{total}'); return total
 @staticmethod
 def is_temporary(msg):
  vals=[getattr(msg,'ttl_period',None),getattr(getattr(msg,'media',None),'ttl_seconds',None),getattr(getattr(msg,'media',None),'ttl_period',None)]
  return any(isinstance(v,int) and v>0 for v in vals)
 async def _save(self,msg,kind,sender):
  save_message(msg.chat_id,msg.id,getattr(sender,'id',self.owner_id),getattr(sender,'first_name','') or '',getattr(sender,'username','') or '',kind,msg.raw_text or '',type(getattr(msg,'media',None)).__name__ if msg.media else None,None,msg.date.timestamp() if msg.date else time.time())
 async def on_incoming(self,e):
  msg=e.message; sender=await e.get_sender(); sid=getattr(sender,'id',None)
  if sid and db.muted(sid):
   try: await msg.delete()
   except Exception:pass
   return
  if e.is_private and db.get_setting('private_lock','0')=='1' and sid and not db.private_exception(self.owner_id,sid):
   try: await msg.delete()
   except Exception:pass
   return
  await self._save(msg,'incoming',sender)
  if e.is_private and self.is_temporary(msg) and msg.media: await self.capture_temporary(msg)
 async def on_outgoing(self,e):
  me=await self.client.get_me(); await self._save(e.message,'outgoing',me)
 async def on_edited(self,e):
  m=e.message; db.run('UPDATE message_archive SET text=?,edited_at=? WHERE chat_id=? AND message_id=?',(m.raw_text or '',int(time.time()),e.chat_id,m.id)); db.log(self.owner_id,'message_edited',f'{e.chat_id}:{m.id}')
 async def on_deleted(self,e):
  for mid in list(e.deleted_ids or []):
   if db.one('SELECT 1 FROM message_archive WHERE chat_id=? AND message_id=?',(e.chat_id,mid)):
    db.run('UPDATE message_archive SET deleted_at=? WHERE chat_id=? AND message_id=?',(int(time.time()),e.chat_id,mid)); db.log(self.owner_id,'message_deleted',f'{e.chat_id}:{mid}')
 async def capture_temporary(self,msg):
  temp=STORAGE/'temporary'; temp.mkdir(exist_ok=True); path=await msg.download_media(file=str(temp))
  if not path:return
  try:
   await self.client.send_file('me',path,caption=f'⏳ حفظ مؤقت\nChat: {msg.chat_id}\nMessage: {msg.id}')
   db.run('UPDATE message_archive SET media_path=?,kind=? WHERE chat_id=? AND message_id=?',(None,'temporary_incoming',msg.chat_id,msg.id))
   Path(path).unlink(missing_ok=True)
  except Exception as e: log.warning('temporary send failed: %s',e)
 async def import_private(self,chat_id,limit=1000):
  ent=await self.resolve(chat_id); n=0
  async for msg in self.client.iter_messages(ent,limit=limit,reverse=True):
   sender=await msg.get_sender(); await self._save(msg,'imported',sender); n+=1
  db.log(self.owner_id,'import_private',str(chat_id)); return n

manager=UserAutomation()
