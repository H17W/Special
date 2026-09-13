import asyncio,json
from pathlib import Path
from app.core.database import db
from app.core.config import STORAGE
class MimicService:
 def __init__(self,client): self.client=client; self.lock=asyncio.Lock()
 async def start(self,target):
  async with self.lock:
   ent=await self.client.resolve(target); me=await self.client.get_me(); db.set_setting('mimic_backup',json.dumps({'first_name':me.first_name or '','last_name':me.last_name or '','bio':getattr(me,'about','') or ''},ensure_ascii=False)); p=await self.client.download_profile_photo(ent,file=str(STORAGE/'mimic_original')); 
   if p: db.set_setting('mimic_backup_photo',str(p))
   from telethon import functions
   try:
    await self.client(functions.account.UpdateProfileRequest(first_name=ent.first_name or '',last_name=ent.last_name or '',about=getattr(ent,'about','') or '')); newp=await self.client.download_profile_photo(ent,file=str(STORAGE/'mimic_new'))
    if newp: up=await self.client.upload_file(newp); await self.client(functions.photos.UploadProfilePhotoRequest(file=up))
    db.set_setting('mimic_active','1'); return True
   except Exception:
    await self.restore(); raise
 async def restore(self):
  async with self.lock:
   raw=db.get_setting('mimic_backup','');
   if not raw:return False
   b=json.loads(raw); from telethon import functions; await self.client(functions.account.UpdateProfileRequest(first_name=b.get('first_name',''),last_name=b.get('last_name',''),about=b.get('bio','') or ''))
   p=db.get_setting('mimic_backup_photo','')
   if p and Path(p).exists(): up=await self.client.upload_file(p); await self.client(functions.photos.UploadProfilePhotoRequest(file=up))
   db.set_setting('mimic_active','0'); return True
