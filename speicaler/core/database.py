from __future__ import annotations
import sqlite3, threading, time, secrets
from contextlib import contextmanager
from .config import settings

class DB:
    def __init__(self, path=None):
        self.path=path or settings.db_path; self.lock=threading.RLock()
        self._init()
    @contextmanager
    def conn(self):
        with self.lock:
            c=sqlite3.connect(self.path, timeout=30, check_same_thread=False); c.row_factory=sqlite3.Row
            try: yield c; c.commit()
            finally: c.close()
    def _init(self):
        with self.conn() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, status TEXT NOT NULL DEFAULT 'pending', expires_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS access_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reason TEXT, created_at INTEGER NOT NULL, handled_at INTEGER);
            CREATE TABLE IF NOT EXISTS restrictions(user_id INTEGER PRIMARY KEY, until_at INTEGER, permanent INTEGER NOT NULL DEFAULT 0, reason TEXT, updated_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feature_permissions(user_id INTEGER NOT NULL, feature TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(user_id,feature));
            CREATE TABLE IF NOT EXISTS private_exceptions(user_id INTEGER NOT NULL, target_id INTEGER NOT NULL, PRIMARY KEY(user_id,target_id));
            CREATE TABLE IF NOT EXISTS bot_exceptions(target_id INTEGER PRIMARY KEY, reason TEXT);
            CREATE TABLE IF NOT EXISTS muted_users(target_id INTEGER PRIMARY KEY, username TEXT, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS start_abuse(user_id INTEGER PRIMARY KEY, attempts INTEGER NOT NULL DEFAULT 0, last_at INTEGER NOT NULL DEFAULT 0, notify_at INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS temp_links(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at INTEGER NOT NULL, grant_seconds INTEGER NOT NULL DEFAULT 86400, max_uses INTEGER NOT NULL DEFAULT 1, uses INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS delete_sessions(user_id INTEGER PRIMARY KEY, target_chat_id INTEGER, start_message_id INTEGER, updated_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS keyboard_sessions(chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL, owner_id INTEGER NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(chat_id,message_id));
            CREATE TABLE IF NOT EXISTS keyboard_abuse(user_id INTEGER PRIMARY KEY, attempts INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS audio_jobs(user_id INTEGER PRIMARY KEY, path TEXT, title TEXT, artist TEXT, cover TEXT, updated_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS message_archive(chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL, sender_id INTEGER, kind TEXT, text TEXT, media_path TEXT, created_at INTEGER NOT NULL, edited_at INTEGER, PRIMARY KEY(chat_id,message_id));
            CREATE TABLE IF NOT EXISTS operation_log(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, detail TEXT, created_at INTEGER NOT NULL);
            ''')
    def one(self,q,p=()):
        with self.conn() as c: return c.execute(q,p).fetchone()
    def all(self,q,p=()):
        with self.conn() as c: return c.execute(q,p).fetchall()
    def run(self,q,p=()):
        with self.conn() as c: return c.execute(q,p).rowcount
    def log(self,uid,action,detail=''): self.run('INSERT INTO operation_log(user_id,action,detail,created_at) VALUES(?,?,?,?)',(uid,action,detail,int(time.time())))
    def upsert_user(self,uid,username='',first_name=''):
        now=int(time.time()); self.run('INSERT INTO users(id,username,first_name,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,updated_at=excluded.updated_at',(uid,username or '',first_name or '',now,now))
    def user(self,uid): return self.one('SELECT * FROM users WHERE id=?',(uid,))
    def access_active(self,uid):
        if uid==settings.owner_id:return True
        r=self.user(uid); return bool(r and r['status']=='active' and (r['expires_at'] is None or r['expires_at']>int(time.time())))
    def request_access(self,uid):
        r=self.one("SELECT id FROM access_requests WHERE user_id=? AND status='pending'",(uid,))
        if r:return r['id']
        return self.run('INSERT INTO access_requests(user_id,created_at) VALUES(?,?)',(uid,int(time.time())))
    def pending_requests(self): return self.all("SELECT * FROM access_requests WHERE status='pending' ORDER BY created_at")
    def decide_request(self,rid,uid,accept,expires_at=None,reason=None):
        now=int(time.time()); status='accepted' if accept else 'rejected'
        self.run('UPDATE access_requests SET status=?,reason=?,handled_at=? WHERE id=?',(status,reason,now,rid))
        if accept:self.run("UPDATE users SET status='active',expires_at=?,updated_at=? WHERE id=?",(expires_at,now,uid))
        else:self.run("UPDATE users SET status='rejected',updated_at=? WHERE id=?",(now,uid))
    def restrict(self,uid,seconds=None,permanent=False,reason=''):
        until=None if permanent else int(time.time())+int(seconds or 0); self.run('INSERT INTO restrictions(user_id,until_at,permanent,reason,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET until_at=excluded.until_at,permanent=excluded.permanent,reason=excluded.reason,updated_at=excluded.updated_at',(uid,until,int(permanent),reason,int(time.time())))
    def unrestricted(self,uid):
        r=self.one('SELECT * FROM restrictions WHERE user_id=?',(uid,));
        if not r:return True
        if r['permanent']:return False
        if r['until_at'] and r['until_at']>int(time.time()):return False
        self.run('DELETE FROM restrictions WHERE user_id=?',(uid,)); return True
    def remaining_restriction(self,uid):
        r=self.one('SELECT * FROM restrictions WHERE user_id=?',(uid,));
        if not r:return 0
        return -1 if r['permanent'] else max(0,r['until_at']-int(time.time()))
    def set_setting(self,k,v): self.run('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(v)))
    def get_setting(self,k,default='0'):
        r=self.one('SELECT value FROM settings WHERE key=?',(k,)); return r['value'] if r else default
    def feature(self,uid,k):
        r=self.one('SELECT enabled FROM feature_permissions WHERE user_id=? AND feature=?',(uid,k)); return True if not r else bool(r['enabled'])
    def set_feature(self,uid,k,e): self.run('INSERT INTO feature_permissions(user_id,feature,enabled) VALUES(?,?,?) ON CONFLICT(user_id,feature) DO UPDATE SET enabled=excluded.enabled',(uid,k,int(e)))
    def add_private_exception(self,uid,target): self.run('INSERT OR IGNORE INTO private_exceptions(user_id,target_id) VALUES(?,?)',(uid,target))
    def del_private_exception(self,uid,target): self.run('DELETE FROM private_exceptions WHERE user_id=? AND target_id=?',(uid,target))
    def private_exception(self,uid,target): return bool(self.one('SELECT 1 FROM private_exceptions WHERE user_id=? AND target_id=?',(uid,target)))
    def mute(self,target,username=''): self.run('INSERT OR REPLACE INTO muted_users(target_id,username,created_at) VALUES(?,?,?)',(target,username,int(time.time())))
    def unmute(self,target): self.run('DELETE FROM muted_users WHERE target_id=?',(target,))
    def muted(self,target): return bool(self.one('SELECT 1 FROM muted_users WHERE target_id=?',(target,)))
    def create_link(self,uid,seconds,max_uses=1,grant_seconds=86400):
        token=secrets.token_urlsafe(24); self.run('INSERT INTO temp_links(token,user_id,expires_at,grant_seconds,max_uses) VALUES(?,?,?,?,?)',(token,uid,int(time.time())+seconds,int(grant_seconds),max_uses)); return token
    def consume_link(self,token):
        r=self.one('SELECT * FROM temp_links WHERE token=?',(token,));
        if not r or r['expires_at']<=int(time.time()) or r['uses']>=r['max_uses']: return None
        self.run('UPDATE temp_links SET uses=uses+1 WHERE token=?',(token,)); return (r['user_id'],int(r['grant_seconds']))
    def set_delete_start(self,uid,chat,msg): self.run('INSERT INTO delete_sessions(user_id,target_chat_id,start_message_id,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET target_chat_id=excluded.target_chat_id,start_message_id=excluded.start_message_id,updated_at=excluded.updated_at',(uid,chat,msg,int(time.time())))
    def delete_session(self,uid): return self.one('SELECT * FROM delete_sessions WHERE user_id=?',(uid,))
    def clear_delete(self,uid): self.run('DELETE FROM delete_sessions WHERE user_id=?',(uid,))
    def keyboard_abuse(self,uid):
        r=self.one('SELECT attempts FROM keyboard_abuse WHERE user_id=?',(uid,)); return int(r['attempts']) if r else 0
    def add_keyboard_abuse(self,uid):
        n=self.keyboard_abuse(uid)+1; self.run('INSERT INTO keyboard_abuse(user_id,attempts,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET attempts=excluded.attempts,updated_at=excluded.updated_at',(uid,n,int(time.time()))); return n
    def stats(self):
        return {k:self.one(q)[0] for k,q in {'users':'SELECT COUNT(*) FROM users','active':'SELECT COUNT(*) FROM users WHERE status="active"','requests':'SELECT COUNT(*) FROM access_requests WHERE status="pending"','muted':'SELECT COUNT(*) FROM muted_users','logs':'SELECT COUNT(*) FROM operation_log'}.items()}

    def cleanup_expired(self):
        now=int(time.time())
        self.run('DELETE FROM temp_links WHERE expires_at<=? OR uses>=max_uses',(now,))
        self.run('DELETE FROM restrictions WHERE permanent=0 AND until_at IS NOT NULL AND until_at<=?',(now,))
        self.run("UPDATE users SET status='expired' WHERE status='active' AND expires_at IS NOT NULL AND expires_at<=?",(now,))

db=DB()
