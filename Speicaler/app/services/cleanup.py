import time
from app.core.database import db
from app.core.config import STORAGE
DEFAULTS={'operations':604800,'private_log':2592000,'access':2592000,'broadcast':2592000,'storage':2592000}
def clean(category,seconds=None):
 seconds=int(seconds or DEFAULTS.get(category,2592000)); n=db.cleanup_category(category,seconds)
 if category=='storage' and STORAGE.exists():
  cutoff=time.time()-seconds
  for p in STORAGE.rglob('*'):
   if p.is_file():
    try:
     if p.stat().st_mtime<cutoff:p.unlink()
    except OSError:pass
 return n
def counts(): return db.cleanup_counts()
