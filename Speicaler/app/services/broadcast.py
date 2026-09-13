import asyncio,time
from app.core.database import db
from app.core.config import settings
async def run_broadcast(bot,text,targets,job_id):
 sent=failed=0; db.run('UPDATE broadcast_jobs SET status=?,started_at=? WHERE id=?',('running',int(time.time()),job_id))
 for uid in targets:
  try: await bot.send_message(uid,text); sent+=1
  except Exception: failed+=1
  await asyncio.sleep(.05)
 db.run('UPDATE broadcast_jobs SET status=?,finished_at=?,sent=?,failed=? WHERE id=?',('done',int(time.time()),sent,failed,job_id)); db.log(settings.owner_id,'broadcast_finished',f'{job_id}:{sent}:{failed}'); return sent,failed
