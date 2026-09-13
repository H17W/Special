from __future__ import annotations
from .config import settings
from .database import db

def is_owner(uid:int)->bool:return int(uid)==settings.owner_id

def allowed(uid:int,feature=None)->bool:
    if is_owner(uid): return True
    if not db.access_active(uid) or not db.unrestricted(uid): return False
    return feature is None or db.feature(uid,feature)
