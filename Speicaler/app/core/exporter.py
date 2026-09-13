from __future__ import annotations
import json, time
from pathlib import Path
from .config import BACKUPS
from .database import db

def export_backup()->Path:
    data={'created_at':int(time.time()),'stats':db.stats(),'users':[dict(x) for x in db.all('SELECT * FROM users')],'settings':[dict(x) for x in db.all('SELECT * FROM settings')]}
    p=BACKUPS/f'special-backup-{int(time.time())}.json'; p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); return p
