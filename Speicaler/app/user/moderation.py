from app.core.database import db

def mute(target,username=''): db.mute(int(target),username)
def unmute(target): db.unmute(int(target))
def is_muted(target): return db.muted(int(target))
def get_all_muted_users(): return db.all('SELECT * FROM muted_users ORDER BY created_at DESC')
