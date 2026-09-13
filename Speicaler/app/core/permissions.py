from .config import settings
from .database import db

def is_owner(uid): return int(uid)==int(settings.owner_id)
def allowed(uid,feature=None):
    if is_owner(uid): return True
    if not db.access_active(uid) or not db.unrestricted(uid): return False
    return True if not feature else db.feature(uid,feature)
