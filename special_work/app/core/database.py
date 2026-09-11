import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from .permissions import FEATURE_KEYS

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "special.db"
BACKUP_DIR = ROOT / "backups"
MEDIA_DIR = ROOT / "storage" / "media"

def get_connection():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def _now(): return datetime.now(timezone.utc).isoformat()

def init_database():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True); MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS muted_users(user_id INTEGER PRIMARY KEY,username TEXT,display_name TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS private_chats(user_id INTEGER PRIMARY KEY,username TEXT,display_name TEXT,last_seen TEXT,message_count INTEGER DEFAULT 0,photo_count INTEGER DEFAULT 0,video_count INTEGER DEFAULT 0,sticker_count INTEGER DEFAULT 0,gif_count INTEGER DEFAULT 0,link_count INTEGER DEFAULT 0,audio_count INTEGER DEFAULT 0,file_count INTEGER DEFAULT 0,broadcast_allowed INTEGER DEFAULT 1,archived INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_message_id INTEGER,user_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,direction TEXT NOT NULL,text TEXT,media_type TEXT,media_path TEXT,message_date TEXT,edited_at TEXT,deleted_at TEXT,UNIQUE(chat_id,telegram_message_id,direction));
        CREATE TABLE IF NOT EXISTS important_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,message_id INTEGER NOT NULL UNIQUE,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS broadcast_exclusions(user_id INTEGER PRIMARY KEY,username TEXT,display_name TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS broadcast_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,text TEXT,total_targets INTEGER DEFAULT 0,sent_count INTEGER DEFAULT 0,failed_count INTEGER DEFAULT 0,started_at TEXT,finished_at TEXT,status TEXT DEFAULT 'completed');
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS allowed_users(user_id INTEGER PRIMARY KEY,username TEXT,display_name TEXT,status TEXT NOT NULL DEFAULT 'active',access_until TEXT,suspended_until TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS feature_permissions(user_id INTEGER NOT NULL,feature_key TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,feature_key),FOREIGN KEY(user_id) REFERENCES allowed_users(user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS security_log(id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT,description TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS operation_log(id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT,description TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS scheduled_broadcasts(id INTEGER PRIMARY KEY AUTOINCREMENT,text TEXT,run_at TEXT,status TEXT DEFAULT 'scheduled',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        c.commit()
    ensure_default_settings()

def ensure_default_settings():
    defaults={"ownership_protection":"0","media_protection":"0","notify_deleted":"1","notify_edited":"1","notify_new_contact":"1"}
    with get_connection() as c:
        for k,v in defaults.items(): c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
        c.commit()

def mute_user(user_id,username=None,display_name=None):
    with get_connection() as c: c.execute("INSERT OR REPLACE INTO muted_users(user_id,username,display_name) VALUES(?,?,?)",(user_id,username,display_name)); c.commit()
def unmute_user(user_id):
    with get_connection() as c: cur=c.execute("DELETE FROM muted_users WHERE user_id=?",(user_id,)); c.commit(); return cur.rowcount>0
def is_muted(user_id):
    with get_connection() as c: return c.execute("SELECT 1 FROM muted_users WHERE user_id=?",(user_id,)).fetchone() is not None
def get_all_muted_users():
    with get_connection() as c: return c.execute("SELECT * FROM muted_users ORDER BY created_at DESC").fetchall()

def upsert_private_chat(user_id,username,display_name):
    with get_connection() as c:
        c.execute("INSERT INTO private_chats(user_id,username,display_name,last_seen) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,display_name=excluded.display_name,last_seen=excluded.last_seen",(user_id,username,display_name,_now())); c.commit()
def add_message(telegram_message_id,user_id,chat_id,direction,text,media_type,media_path,message_date):
    with get_connection() as c:
        cur=c.execute("INSERT OR IGNORE INTO messages(telegram_message_id,user_id,chat_id,direction,text,media_type,media_path,message_date) VALUES(?,?,?,?,?,?,?,?)",(telegram_message_id,user_id,chat_id,direction,text,media_type,media_path,message_date)); c.commit()
        if cur.lastrowid:return cur.lastrowid
        r=c.execute("SELECT id FROM messages WHERE chat_id=? AND telegram_message_id=? AND direction=?",(chat_id,telegram_message_id,direction)).fetchone(); return r["id"] if r else None
def mark_message_edited(telegram_message_id,chat_id,direction,new_text):
    with get_connection() as c:c.execute("UPDATE messages SET text=?,edited_at=? WHERE telegram_message_id=? AND chat_id=? AND direction=?",(new_text,_now(),telegram_message_id,chat_id,direction));c.commit()
def mark_message_deleted(telegram_message_id,chat_id,direction):
    with get_connection() as c:c.execute("UPDATE messages SET deleted_at=? WHERE telegram_message_id=? AND chat_id=? AND direction=?",(_now(),telegram_message_id,chat_id,direction));c.commit()
def increment_stats(user_id,media_type=None,has_link=False):
    fields=["message_count=message_count+1"]
    mapping={"photo":"photo_count","video":"video_count","sticker":"sticker_count","gif":"gif_count","audio":"audio_count","file":"file_count"}
    if media_type in mapping:fields.append(mapping[media_type]+"="+mapping[media_type]+"+1")
    if has_link:fields.append("link_count=link_count+1")
    with get_connection() as c:c.execute(f"UPDATE private_chats SET {','.join(fields)},last_seen=? WHERE user_id=?",(_now(),user_id));c.commit()
def list_private_chats():
    with get_connection() as c:return c.execute("SELECT * FROM private_chats ORDER BY archived ASC,last_seen DESC").fetchall()
def get_private_chat(user_id):
    with get_connection() as c:return c.execute("SELECT * FROM private_chats WHERE user_id=?",(user_id,)).fetchone()
def list_messages(user_id,limit=30,offset=0):
    with get_connection() as c:return c.execute("SELECT * FROM messages WHERE user_id=? ORDER BY message_date ASC LIMIT ? OFFSET ?",(user_id,limit,offset)).fetchall()
def search_messages(user_id,text):
    with get_connection() as c:return c.execute("SELECT * FROM messages WHERE user_id=? AND text LIKE ? ORDER BY message_date DESC LIMIT 50",(user_id,f"%{text}%")).fetchall()
def mark_important(message_id):
    with get_connection() as c:c.execute("INSERT OR IGNORE INTO important_messages(message_id) VALUES(?)",(message_id,));c.commit()
def important_messages():
    with get_connection() as c:return c.execute("SELECT m.* FROM messages m JOIN important_messages i ON i.message_id=m.id ORDER BY i.created_at DESC").fetchall()
def find_exact_message(user_id,text):
    with get_connection() as c:return c.execute("SELECT * FROM messages WHERE user_id=? AND text=? ORDER BY message_date DESC LIMIT 10",(user_id,text)).fetchall()

def is_broadcast_excluded(user_id):
    with get_connection() as c:return c.execute("SELECT 1 FROM broadcast_exclusions WHERE user_id=?",(user_id,)).fetchone() is not None
def set_broadcast_exclusion(user_id,username=None,display_name=None):
    with get_connection() as c:c.execute("INSERT OR REPLACE INTO broadcast_exclusions(user_id,username,display_name) VALUES(?,?,?)",(user_id,username,display_name));c.commit()
def remove_broadcast_exclusion(user_id):
    with get_connection() as c:cur=c.execute("DELETE FROM broadcast_exclusions WHERE user_id=?",(user_id,));c.commit();return cur.rowcount>0
def list_broadcast_exclusions():
    with get_connection() as c:return c.execute("SELECT * FROM broadcast_exclusions ORDER BY created_at DESC").fetchall()
def broadcast_targets():
    with get_connection() as c:return c.execute("SELECT p.* FROM private_chats p WHERE p.broadcast_allowed=1 AND p.user_id NOT IN (SELECT user_id FROM broadcast_exclusions) ORDER BY p.last_seen DESC").fetchall()
def set_broadcast_allowed(user_id,allowed):
    with get_connection() as c:c.execute("UPDATE private_chats SET broadcast_allowed=? WHERE user_id=?",(1 if allowed else 0,user_id));c.commit()
def add_broadcast_log(text,total_targets,sent_count,failed_count,started_at,finished_at,status="completed"):
    with get_connection() as c:cur=c.execute("INSERT INTO broadcast_logs(text,total_targets,sent_count,failed_count,started_at,finished_at,status) VALUES(?,?,?,?,?,?,?)",(text,total_targets,sent_count,failed_count,started_at,finished_at,status));c.commit();return cur.lastrowid
def list_broadcast_logs(limit=30):
    with get_connection() as c:return c.execute("SELECT * FROM broadcast_logs ORDER BY id DESC LIMIT ?",(limit,)).fetchall()

def set_setting(key,value):
    with get_connection() as c:c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",(key,str(value)));c.commit()
def get_setting(key,default=None):
    with get_connection() as c:r=c.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone();return r["value"] if r else default

def add_allowed_user(user_id,username,display_name,access_until):
    with get_connection() as c:c.execute("INSERT OR REPLACE INTO allowed_users(user_id,username,display_name,status,access_until,suspended_until) VALUES(?,?,?,?,?,NULL)",(user_id,username,display_name,"active",access_until));c.commit();ensure_feature_permissions(user_id)
def get_allowed_users():
    expire_access_users()
    with get_connection() as c:return c.execute("SELECT * FROM allowed_users ORDER BY created_at DESC").fetchall()
def get_allowed_user(user_id):
    expire_access_users()
    with get_connection() as c:return c.execute("SELECT * FROM allowed_users WHERE user_id=?",(user_id,)).fetchone()
def update_allowed_status(user_id,status,suspended_until=None):
    with get_connection() as c:c.execute("UPDATE allowed_users SET status=?,suspended_until=? WHERE user_id=?",(status,suspended_until,user_id));c.commit()
def remove_allowed_user(user_id):
    with get_connection() as c:cur=c.execute("DELETE FROM allowed_users WHERE user_id=?",(user_id,));c.commit();return cur.rowcount>0
def expire_access_users():
    now=datetime.now(timezone.utc).isoformat()
    with get_connection() as c:
        c.execute("UPDATE allowed_users SET status='expired' WHERE access_until IS NOT NULL AND access_until!='' AND access_until<? AND status='active'",(now,))
        c.execute("UPDATE allowed_users SET status='active',suspended_until=NULL WHERE suspended_until IS NOT NULL AND suspended_until<=? AND status='suspended'",(now,));c.commit()

def add_log(table,event_type,description):
    if table not in {"security_log","operation_log"}:raise ValueError("invalid log table")
    with get_connection() as c:c.execute(f"INSERT INTO {table}(event_type,description) VALUES(?,?)",(event_type,description));c.commit()
def get_logs(table,limit=50):
    if table not in {"security_log","operation_log"}:raise ValueError("invalid log table")
    with get_connection() as c:return c.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?",(limit,)).fetchall()

def ensure_feature_permissions(user_id):
    # feature_permissions references allowed_users(user_id), so the parent
    # row must exist before inserting permissions.
    if not user_id:
        return
    with get_connection() as c:
        c.execute(
            "INSERT OR IGNORE INTO allowed_users(user_id,username,display_name,status,access_until,suspended_until) VALUES(?,?,?,?,?,NULL)",
            (user_id, None, str(user_id), "active", None)
        )
        for key in FEATURE_KEYS:
            c.execute(
                "INSERT OR IGNORE INTO feature_permissions(user_id,feature_key,enabled) VALUES(?,?,1)",
                (user_id, key)
            )
        c.commit()

def get_feature_permissions(user_id):
    ensure_feature_permissions(user_id)
    with get_connection() as c:rows=c.execute("SELECT feature_key,enabled FROM feature_permissions WHERE user_id=?",(user_id,)).fetchall()
    return {r["feature_key"]:bool(r["enabled"]) for r in rows}
def is_feature_enabled(user_id,feature_key):
    ensure_feature_permissions(user_id)
    with get_connection() as c:r=c.execute("SELECT enabled FROM feature_permissions WHERE user_id=? AND feature_key=?",(user_id,feature_key)).fetchone();return bool(r["enabled"]) if r else True
def set_feature_permission(user_id,feature_key,enabled):
    with get_connection() as c:c.execute("INSERT INTO feature_permissions(user_id,feature_key,enabled,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,feature_key) DO UPDATE SET enabled=excluded.enabled,updated_at=excluded.updated_at",(user_id,feature_key,1 if enabled else 0,_now()));c.commit()
def set_all_feature_permissions(user_id,enabled):
    ensure_feature_permissions(user_id)
    with get_connection() as c:c.execute("UPDATE feature_permissions SET enabled=?,updated_at=? WHERE user_id=?",(1 if enabled else 0,_now(),user_id));c.commit()

def add_scheduled_broadcast(text,run_at):
    with get_connection() as c:cur=c.execute("INSERT INTO scheduled_broadcasts(text,run_at,status) VALUES(?,?,?)",(text,run_at,"scheduled"));c.commit();return cur.lastrowid
def list_scheduled_broadcasts():
    with get_connection() as c:return c.execute("SELECT * FROM scheduled_broadcasts ORDER BY run_at").fetchall()
def cancel_scheduled_broadcast(item_id):
    with get_connection() as c:cur=c.execute("UPDATE scheduled_broadcasts SET status='cancelled' WHERE id=? AND status='scheduled'",(item_id,));c.commit();return cur.rowcount>0
