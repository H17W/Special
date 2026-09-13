from __future__ import annotations
import asyncio, re
from pathlib import Path
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon import functions
from app.core.config import settings, STORAGE
from app.core.database import db
from app.core.logger import log

TEMP_RE=re.compile(r'(?:self.?destruct|view.?once|ttl|timer)',re.I)

class UserAutomation:
    def __init__(self):
        self.client=TelegramClient(str(STORAGE/settings.session_name),settings.api_id,settings.api_hash)
        self.login_phone=None; self.login_hash=None
        self.owner_id=settings.owner_id
        self.mimic_lock=asyncio.Lock()
        self._register_events()
    def _register_events(self):
        @self.client.on(events.NewMessage(incoming=True))
        async def incoming(e): await self.on_incoming(e)
        @self.client.on(events.NewMessage(outgoing=True))
        async def outgoing(e): await self.on_outgoing(e)
        @self.client.on(events.MessageEdited())
        async def edited(e): await self.on_edited(e)
        @self.client.on(events.MessageDeleted())
        async def deleted(e): await self.on_deleted(e)
    async def start(self):
        if not self.client.is_connected(): await self.client.connect()
        if await self.client.is_user_authorized():
            me=await self.client.get_me(); self.owner_id=me.id; return True
        return False
    async def send_code(self,phone):
        await self.client.connect(); r=await self.client.send_code_request(phone); self.login_phone=phone; self.login_hash=r.phone_code_hash; return True
    async def sign_in_code(self,code):
        if not self.login_phone or not self.login_hash: raise RuntimeError('لا توجد عملية تسجيل دخول معلقة')
        try:
            await self.client.sign_in(self.login_phone,code,phone_code_hash=self.login_hash)
        except SessionPasswordNeededError:
            return 'PASSWORD_REQUIRED'
        self.login_phone=self.login_hash=None; return 'OK'
    async def sign_in_password(self,password):
        await self.client.sign_in(password=password); self.login_phone=self.login_hash=None; return 'OK'
    async def stop(self): await self.client.disconnect()
    @staticmethod
    def is_private(e): return bool(e.is_private and not e.out)
    @staticmethod
    def is_temporary(msg):
        vals=[getattr(msg,'ttl_period',None),getattr(getattr(msg,'media',None),'ttl_seconds',None),getattr(getattr(msg,'media',None),'ttl_period',None)]
        return any(isinstance(v,int) and v>0 for v in vals)
    async def on_incoming(self,e):
        msg=e.message; sender=await e.get_sender(); sid=getattr(sender,'id',None)
        if sid and db.muted(sid):
            try: await msg.delete()
            except Exception: pass
            return
        if e.is_private:
            if db.get_setting('private_lock','0')=='1' and sid and not db.private_exception(self.owner_id,sid):
                try: await msg.delete()
                except Exception: pass
                return
            if db.get_setting('profanity_filter','0')=='1' and isinstance(msg.raw_text,str) and contains_profanity(msg.raw_text):
                try: await msg.delete()
                except Exception: pass
                return
        # Only incoming temporary media is archived. Normal media is deliberately ignored.
        if sid:
            db.run('INSERT OR REPLACE INTO message_archive(chat_id,message_id,sender_id,kind,text,created_at) VALUES(?,?,?,?,?,?)',(e.chat_id,msg.id,sid,'incoming',msg.raw_text or '',int(msg.date.timestamp())))
        # Archive temporary media only after the message record exists.
        if e.is_private and self.is_temporary(msg) and msg.media:
            await self.archive_temp(msg)
    async def on_outgoing(self,e):
        msg=e.message
        db.run('INSERT OR REPLACE INTO message_archive(chat_id,message_id,sender_id,kind,text,created_at) VALUES(?,?,?,?,?,?)',(e.chat_id,msg.id,self.owner_id,'outgoing',msg.raw_text or '',int(msg.date.timestamp())))
    async def on_edited(self,e):
        msg=e.message
        old=db.one('SELECT text FROM message_archive WHERE chat_id=? AND message_id=?',(e.chat_id,msg.id))
        if not old:return
        new=msg.raw_text or ''
        if old['text']==new:return
        db.run('UPDATE message_archive SET text=?,edited_at=? WHERE chat_id=? AND message_id=?',(new,int(msg.edit_date.timestamp()) if msg.edit_date else int(msg.date.timestamp()),e.chat_id,msg.id))
        db.log(self.owner_id,'message_edited',f'{e.chat_id}:{msg.id}')
    async def on_deleted(self,e):
        ids=list(e.deleted_ids or [])
        for mid in ids:
            row=db.one('SELECT * FROM message_archive WHERE chat_id=? AND message_id=?',(e.chat_id,mid))
            if row:
                db.log(self.owner_id,'message_deleted',f'{e.chat_id}:{mid}')
                db.run('DELETE FROM message_archive WHERE chat_id=? AND message_id=?',(e.chat_id,mid))
    async def archive_temp(self,msg):
        try:
            target=STORAGE/'temporary'; target.mkdir(exist_ok=True)
            path=await msg.download_media(file=str(target))
            if path: db.run('UPDATE message_archive SET media_path=?,kind=? WHERE chat_id=? AND message_id=?',(str(path),'temporary_incoming',msg.chat_id,msg.id))
        except Exception as ex: log.warning('temporary media archive failed: %s',ex)
    async def resolve(self,target):
        # Always resolve numeric IDs through Telethon so profile/media APIs
        # receive a real entity instead of a bare integer.
        if isinstance(target,int) or (isinstance(target,str) and target.lstrip('-').isdigit()):
            return await self.client.get_entity(int(target))
        return await self.client.get_entity(target)
    async def mimic(self,target):
        import json

        async with self.mimic_lock:
            return await self._mimic_unlocked(target)

    async def _mimic_unlocked(self,target):
        import json

        # Do not overwrite a live backup. The user must explicitly restore first.
        if db.get_setting("mimic_active","0") == "1":
            raise RuntimeError("التقليد شغال بالفعل، استخدم الغاء التقليد أولاً")

        ent=await self.resolve(target)
        me=await self.client.get_me()

        if getattr(ent,"bot",False):
            raise RuntimeError("لا يمكن تقليد حساب بوت")
        if getattr(ent,"id",None) == getattr(me,"id",None):
            raise RuntimeError("ما تقدر تقلد حسابك نفسه")

        original_photo=STORAGE/"mimic_original_profile.jpg"
        target_photo=STORAGE/"mimic_target_profile.jpg"
        original_photo.unlink(missing_ok=True)
        target_photo.unlink(missing_ok=True)

        backup={
            "first_name":getattr(me,"first_name","") or "",
            "last_name":getattr(me,"last_name","") or "",
            "bio":getattr(me,"about","") or "",
            "had_photo":False,
        }

        # Snapshot the owner's profile before changing anything.
        try:
            photos=await self.client.get_profile_photos(me,limit=1)
            if photos:
                path=await self.client.download_profile_photo(me,file=str(original_photo))
                backup["had_photo"]=bool(path and Path(path).exists())
        except Exception as ex:
            log.warning("mimic original photo backup failed: %s",ex)
            backup["had_photo"]=False

        db.set_setting("mimic_backup",json.dumps(backup,ensure_ascii=False))

        try:
            # Download target photo before changing the owner's profile.
            photo=await self.client.download_profile_photo(ent,file=str(target_photo))

            await self.client(functions.account.UpdateProfileRequest(
                first_name=getattr(ent,"first_name","") or "",
                last_name=getattr(ent,"last_name","") or "",
                about=getattr(ent,"about","") or "",
            ))

            if photo and Path(photo).exists():
                uploaded=await self.client.upload_file(str(photo))
                await self.client(functions.photos.UploadProfilePhotoRequest(file=uploaded))
            else:
                await self._delete_profile_photos()

            db.set_setting("mimic_active","1")
            db.set_setting("mimic_target",str(ent.id))
            db.log(self.owner_id,"mimic_start",str(ent.id))
            return ent

        except Exception:
            # If activation fails halfway through, restore the snapshot.
            try:
                await self._restore_mimic_unlocked()
            except Exception as restore_error:
                log.error("mimic rollback failed: %s",restore_error)
            raise

    async def _restore_mimic_unlocked(self):
        import json

        raw=db.get_setting("mimic_backup","")
        if not raw:
            db.set_setting("mimic_active","0")
            db.set_setting("mimic_target","")
            return False

        try:
            b=json.loads(raw)
        except Exception:
            b={"first_name":"","last_name":"","bio":"","had_photo":False}

        await self.client(functions.account.UpdateProfileRequest(
            first_name=b.get("first_name","") or "",
            last_name=b.get("last_name","") or "",
            about=b.get("bio","") or "",
        ))

        original_photo=Path(STORAGE/"mimic_original_profile.jpg")

        # Remove the current mimic photo first, then restore the exact snapshot.
        await self._delete_profile_photos()

        if b.get("had_photo") and original_photo.exists():
            uploaded=await self.client.upload_file(str(original_photo))
            await self.client(functions.photos.UploadProfilePhotoRequest(file=uploaded))

        Path(STORAGE/"mimic_target_profile.jpg").unlink(missing_ok=True)
        db.set_setting("mimic_active","0")
        db.set_setting("mimic_target","")
        db.log(self.owner_id,"mimic_restore","original_profile")
        return True

    async def restore_mimic(self):
        async with self.mimic_lock:
            return await self._restore_mimic_unlocked()

    async def mute(self,target):
        ent=await self.resolve(target); db.mute(ent.id,getattr(ent,'username','') or ''); return ent
    async def unmute(self,target):
        ent=await self.resolve(target); db.unmute(ent.id); return ent
    async def delete_range(self,chat_id,start_id,end_id):
        ent=await self.resolve(chat_id); start,end=sorted((int(start_id),int(end_id)))
        if start < 1 or end < 1:
            raise ValueError("message ids must be positive")
        if not await self.can_delete(chat_id):
            raise PermissionError("No permission to delete messages")
        deleted=0
        # Telegram accepts message ids directly; chunk requests to avoid oversized calls.
        for base in range(start,end+1,100):
            batch=list(range(base,min(end,base+99)+1))
            try:
                await self.client.delete_messages(ent,batch)
                deleted += len(batch)
            except Exception as ex:
                log.warning('delete range batch failed %s: %s',ent,ex)
        return deleted

    async def can_delete(self,chat_id):
        ent=await self.resolve(chat_id)
        if getattr(ent,'broadcast',False) or getattr(ent,'megagroup',False):
            me=await self.client.get_me(); perms=await self.client.get_permissions(ent,me)
            return bool(getattr(perms,'delete_messages',False) or getattr(perms,'is_creator',False))
        return True

def contains_profanity(text:str)->bool:
    # Configurable, conservative Arabic/English insult filter. Expand this list in settings if needed.
    words={'غبي','غبية','تافه','تافهة','حمار','كلب','كلبة','idiot','stupid'}
    normalized=re.sub(r'[\W_]+',' ',text.lower(),flags=re.UNICODE)
    return any(re.search(rf'(?<!\w){re.escape(w)}(?!\w)',normalized) for w in words)

manager=UserAutomation()
