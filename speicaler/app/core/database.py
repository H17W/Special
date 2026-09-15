import sqlite3
from contextvars import ContextVar
from pathlib import Path
from datetime import datetime, timezone, timedelta
from .permissions import FEATURES

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "special.db"
PROFILE_DB_ROOT = ROOT / "storage" / "data"
ACTIVE_PROFILE_ID = ContextVar("special_db_profile_id", default=None)
BACKUP_DIR = ROOT / "backups"
MEDIA_DIR = ROOT / "storage" / "media"


def _now():
    return datetime.now(timezone.utc).isoformat()


def set_active_profile(user_id):
    """Select the private data database for the currently active Telegram account."""
    uid = int(user_id) if user_id is not None else None
    ACTIVE_PROFILE_ID.set(uid)
    if uid is not None:
        init_profile_database(uid)


def active_profile_id():
    return ACTIVE_PROFILE_ID.get()


def profile_db_path(user_id=None):
    uid = active_profile_id() if user_id is None else int(user_id)
    if uid is None:
        return DB_PATH
    root = PROFILE_DB_ROOT / str(uid)
    root.mkdir(parents=True, exist_ok=True)
    return root / "special.db"


def get_connection():
    # Ordinary application data follows the active Telegram account.
    path = profile_db_path()
    c = sqlite3.connect(path, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def get_global_connection():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def _columns(c, table):
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(c, table, column, definition):
    if column not in _columns(c, table):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _initialize_database_at(path):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=30) as c:
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript(
            '''
            CREATE TABLE IF NOT EXISTS muted_users(
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_muted_users(
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id,user_id)
            );
            CREATE TABLE IF NOT EXISTS private_chats(
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                last_seen TEXT,
                message_count INTEGER DEFAULT 0,
                photo_count INTEGER DEFAULT 0,
                video_count INTEGER DEFAULT 0,
                sticker_count INTEGER DEFAULT 0,
                gif_count INTEGER DEFAULT 0,
                link_count INTEGER DEFAULT 0,
                audio_count INTEGER DEFAULT 0,
                file_count INTEGER DEFAULT 0,
                broadcast_allowed INTEGER DEFAULT 1,
                archived INTEGER DEFAULT 0,
                is_bot INTEGER DEFAULT 0,
                is_deleted_user INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_message_id INTEGER,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                direction TEXT NOT NULL,
                text TEXT,
                media_type TEXT,
                media_path TEXT,
                message_date TEXT,
                edited_at TEXT,
                deleted_at TEXT,
                UNIQUE(chat_id,telegram_message_id,direction)
            );
            CREATE TABLE IF NOT EXISTS message_edit_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                telegram_message_id INTEGER,
                chat_id INTEGER,
                user_id INTEGER,
                direction TEXT,
                old_text TEXT,
                new_text TEXT,
                edited_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS important_messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS broadcast_exclusions(
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS broadcast_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                total_targets INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                started_at TEXT,
                finished_at TEXT,
                status TEXT DEFAULT 'completed'
            );
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS allowed_users(
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                access_until TEXT,
                suspended_until TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS feature_permissions(
                user_id INTEGER NOT NULL,
                feature_key TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id,feature_key),
                FOREIGN KEY(user_id) REFERENCES allowed_users(user_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS security_log(id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT,description TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS operation_log(id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT,description TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS scheduled_broadcasts(id INTEGER PRIMARY KEY AUTOINCREMENT,text TEXT,run_at TEXT,status TEXT DEFAULT 'scheduled',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS ai_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                user_id INTEGER,
                display_name TEXT,
                username TEXT,
                chat_id INTEGER,
                chat_type TEXT,
                prompt TEXT,
                answer TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS bot_access_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                display_name TEXT,
                username TEXT,
                status TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS bot_access_attempts(
                user_id INTEGER PRIMARY KEY,
                attempts INTEGER NOT NULL DEFAULT 0,
                notified INTEGER NOT NULL DEFAULT 0,
                user_notified INTEGER NOT NULL DEFAULT 0,
                restricted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_attempt_at TEXT
            );
            CREATE TABLE IF NOT EXISTS user_sessions(
                bot_user_id INTEGER PRIMARY KEY,
                session_path TEXT NOT NULL,
                telegram_user_id INTEGER,
                phone_hint TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            '''
        )
        # Migrations for V10-V14 databases.
        _ensure_column(c, "private_chats", "is_bot", "INTEGER DEFAULT 0")
        _ensure_column(c, "private_chats", "is_deleted_user", "INTEGER DEFAULT 0")
        _ensure_column(c, "bot_access_attempts", "user_notified", "INTEGER DEFAULT 0")
        c.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_msg ON messages(chat_id, telegram_message_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_date ON messages(user_id, message_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_messages_edit ON message_edit_history(chat_id, telegram_message_id, edited_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ai_logs_created ON ai_logs(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_private_name ON private_chats(display_name, username)")
        c.commit()
    return


def _clear_private_data_at(path):
    """Delete all stored private-chat data from one Special database."""
    if not Path(path).exists():
        return
    with sqlite3.connect(path, timeout=30) as c:
        c.execute("PRAGMA foreign_keys=ON")
        # Delete dependent records first so no old private-message remnants remain.
        c.execute("DELETE FROM important_messages")
        c.execute("DELETE FROM message_edit_history")
        c.execute("DELETE FROM messages")
        c.execute("DELETE FROM private_chats")
        # AI logs may contain private-chat prompts/replies. Keep group/channel AI logs.
        c.execute("DELETE FROM ai_logs WHERE lower(COALESCE(chat_type, '')) = 'private' OR source = 'user_account'")
        c.commit()


def clear_all_private_data_once():
    """One-time privacy reset for legacy/mixed private-chat databases."""
    _initialize_database_at(DB_PATH)
    with get_global_connection() as c:
        done = c.execute("SELECT value FROM settings WHERE key='private_data_reset_v18'").fetchone()
        if done and done["value"] == "1":
            return False
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('private_data_reset_v18','1')")
        c.commit()

    paths = [DB_PATH]
    if PROFILE_DB_ROOT.exists():
        paths.extend(PROFILE_DB_ROOT.glob("*/special.db"))
    for path in paths:
        _clear_private_data_at(path)
    return True


def init_database():
    """Initialize the global control DB. Profile DBs are initialized on selection."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    _initialize_database_at(DB_PATH)
    # Global control tables live here.
    ensure_default_settings()
    # FIXED7: wipe all legacy/mixed private data exactly once on first startup.
    clear_all_private_data_once()


def init_profile_database(user_id):
    path = profile_db_path(user_id)
    _initialize_database_at(path)
    # Settings/logs in a profile are intentionally independent.
    with sqlite3.connect(path, timeout=30) as c:
        c.row_factory = sqlite3.Row
        for k, v in {
            "ownership_protection": "0", "media_protection": "0",
            "notify_deleted": "1", "notify_edited": "1",
            "notify_new_contact": "1", "gemini_enabled": "1",
            "gemini_model": "gemini-3.8-flash", "ai_trigger": "",
        }.items():
            c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        c.commit()


def ensure_default_settings():
    defaults = {
        "ownership_protection": "0",
        "media_protection": "0",
        "notify_deleted": "1",
        "notify_edited": "1",
        "notify_new_contact": "1",
        "gemini_enabled": "1",
        "gemini_model": "gemini-3.8-flash",
        "ai_trigger": "",
        "gemini_enabled": "1",
    }
    with get_global_connection() as c:
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        c.commit()


def get_setting(key, default=None):
    connection = get_global_connection if key == "bot_paused" else get_connection
    with connection() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    connection = get_global_connection if key == "bot_paused" else get_connection
    with connection() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))
        c.commit()


def add_log(table, event_type, description):
    if table not in {"operation_log", "security_log"}:
        return
    with get_connection() as c:
        c.execute(f"INSERT INTO {table}(event_type,description) VALUES(?,?)", (event_type, description))
        c.commit()


def get_logs(table, limit=100):
    if table not in {"operation_log", "security_log"}:
        return []
    with get_connection() as c:
        return c.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def mute_user(user_id, username=None, display_name=None):
    with get_connection() as c:
        c.execute("INSERT OR REPLACE INTO muted_users(user_id,username,display_name) VALUES(?,?,?)", (user_id, username, display_name))
        c.commit()


def unmute_user(user_id):
    with get_connection() as c:
        cur = c.execute("DELETE FROM muted_users WHERE user_id=?", (user_id,))
        c.commit()
        return cur.rowcount > 0


def is_muted(user_id):
    with get_connection() as c:
        return c.execute("SELECT 1 FROM muted_users WHERE user_id=?", (user_id,)).fetchone() is not None


def get_all_muted_users():
    with get_connection() as c:
        return c.execute("SELECT * FROM muted_users ORDER BY created_at DESC").fetchall()


def mute_user_in_chat(chat_id, user_id, username=None, display_name=None):
    with get_connection() as c:
        c.execute(
            "INSERT OR REPLACE INTO chat_muted_users(chat_id,user_id,username,display_name) VALUES(?,?,?,?)",
            (chat_id, user_id, username, display_name),
        )
        c.commit()


def unmute_user_in_chat(chat_id, user_id):
    with get_connection() as c:
        cur = c.execute("DELETE FROM chat_muted_users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        c.commit()
        return cur.rowcount > 0


def is_user_muted_in_chat(chat_id, user_id):
    with get_connection() as c:
        return c.execute(
            "SELECT 1 FROM chat_muted_users WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone() is not None


def upsert_private_chat(user_id, username, display_name, is_bot=False, is_deleted_user=False):
    with get_connection() as c:
        c.execute(
            '''INSERT INTO private_chats(user_id,username,display_name,last_seen,is_bot,is_deleted_user)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
               username=excluded.username,
               display_name=excluded.display_name,
               last_seen=excluded.last_seen,
               is_bot=excluded.is_bot,
               is_deleted_user=excluded.is_deleted_user''',
            (user_id, username, display_name, _now(), int(is_bot), int(is_deleted_user)),
        )
        c.commit()


def message_exists(telegram_message_id, chat_id, direction=None):
    with get_connection() as c:
        if direction:
            return c.execute(
                "SELECT 1 FROM messages WHERE telegram_message_id=? AND chat_id=? AND direction=? LIMIT 1",
                (telegram_message_id, chat_id, direction),
            ).fetchone() is not None
        return c.execute(
            "SELECT 1 FROM messages WHERE telegram_message_id=? AND chat_id=? LIMIT 1",
            (telegram_message_id, chat_id),
        ).fetchone() is not None


def insert_message_once(telegram_message_id, user_id, chat_id, direction, text, media_type, media_path, message_date):
    """Return (row_id, inserted). One DB copy per Telegram message id in the chat."""
    with get_connection() as c:
        existing = c.execute(
            "SELECT id FROM messages WHERE chat_id=? AND telegram_message_id=? ORDER BY id ASC LIMIT 1",
            (chat_id, telegram_message_id),
        ).fetchone()
        if existing:
            return existing["id"], False
        cur = c.execute(
            "INSERT INTO messages(telegram_message_id,user_id,chat_id,direction,text,media_type,media_path,message_date) VALUES(?,?,?,?,?,?,?,?)",
            (telegram_message_id, user_id, chat_id, direction, text, media_type, media_path, message_date),
        )
        c.commit()
        return cur.lastrowid, True


def add_message(*args, **kwargs):
    return insert_message_once(*args, **kwargs)[0]


def dedupe_messages():
    with get_connection() as c:
        dupes = c.execute(
            '''SELECT chat_id, telegram_message_id, MIN(id) AS keep_id
               FROM messages
               GROUP BY chat_id, telegram_message_id
               HAVING COUNT(*) > 1'''
        ).fetchall()
        for row in dupes:
            c.execute(
                "DELETE FROM messages WHERE chat_id=? AND telegram_message_id=? AND id<>?",
                (row["chat_id"], row["telegram_message_id"], row["keep_id"]),
            )
        c.commit()


def get_message_record(telegram_message_id, chat_id, direction=None):
    with get_connection() as c:
        if direction:
            return c.execute(
                "SELECT m.*, p.display_name, p.username FROM messages m LEFT JOIN private_chats p ON p.user_id=m.user_id WHERE m.telegram_message_id=? AND m.chat_id=? AND m.direction=? LIMIT 1",
                (telegram_message_id, chat_id, direction),
            ).fetchone()
        return c.execute(
            "SELECT m.*, p.display_name, p.username FROM messages m LEFT JOIN private_chats p ON p.user_id=m.user_id WHERE m.telegram_message_id=? AND m.chat_id=? LIMIT 1",
            (telegram_message_id, chat_id),
        ).fetchone()


def get_private_records_by_message_id(telegram_message_id):
    with get_connection() as c:
        return c.execute(
            "SELECT m.*, p.display_name, p.username FROM messages m LEFT JOIN private_chats p ON p.user_id=m.user_id WHERE m.telegram_message_id=? AND m.chat_id=m.user_id ORDER BY m.id ASC",
            (telegram_message_id,),
        ).fetchall()


def record_edit(telegram_message_id, chat_id, user_id, direction, old_text, new_text):
    with get_connection() as c:
        row = c.execute(
            "SELECT id FROM messages WHERE telegram_message_id=? AND chat_id=? LIMIT 1",
            (telegram_message_id, chat_id),
        ).fetchone()
        c.execute(
            "INSERT INTO message_edit_history(message_id,telegram_message_id,chat_id,user_id,direction,old_text,new_text) VALUES(?,?,?,?,?,?,?)",
            (row["id"] if row else None, telegram_message_id, chat_id, user_id, direction, old_text, new_text),
        )
        c.execute(
            "UPDATE messages SET text=?, edited_at=? WHERE telegram_message_id=? AND chat_id=?",
            (new_text, _now(), telegram_message_id, chat_id),
        )
        c.commit()
        return row["id"] if row else None


def mark_message_edited(telegram_message_id, chat_id, direction, new_text):
    row = get_message_record(telegram_message_id, chat_id, direction)
    if not row:
        return False
    old_text = row["text"] or ""
    new_text = new_text or ""
    # Telegram can emit MessageEdited updates for reaction-related changes.
    # If the message text/caption did not actually change, it is not an edit.
    if old_text == new_text:
        return False
    record_edit(telegram_message_id, chat_id, row["user_id"], direction, old_text, new_text)
    return True


def get_muted_user_by_username(username):
    username = (username or "").strip().lstrip("@").lower()
    if not username:
        return None
    with get_connection() as c:
        return c.execute(
            "SELECT * FROM muted_users WHERE lower(username)=? LIMIT 1",
            (username,),
        ).fetchone()


def get_chat_muted_user_by_username(chat_id, username):
    username = (username or "").strip().lstrip("@").lower()
    if not username:
        return None
    with get_connection() as c:
        return c.execute(
            "SELECT * FROM chat_muted_users WHERE chat_id=? AND lower(username)=? LIMIT 1",
            (chat_id, username),
        ).fetchone()


def mark_message_deleted(telegram_message_id, chat_id=None, direction=None):
    with get_connection() as c:
        if chat_id is None:
            cur = c.execute("UPDATE messages SET deleted_at=? WHERE telegram_message_id=?", (_now(), telegram_message_id))
        elif direction:
            cur = c.execute("UPDATE messages SET deleted_at=? WHERE telegram_message_id=? AND chat_id=? AND direction=?", (_now(), telegram_message_id, chat_id, direction))
        else:
            cur = c.execute("UPDATE messages SET deleted_at=? WHERE telegram_message_id=? AND chat_id=?", (_now(), telegram_message_id, chat_id))
        c.commit()
        return cur.rowcount


def get_messages_by_telegram_ids(telegram_ids, chat_id=None):
    ids = [int(x) for x in telegram_ids if x is not None]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    sql = f"SELECT m.*, p.display_name, p.username FROM messages m LEFT JOIN private_chats p ON p.user_id=m.user_id WHERE m.telegram_message_id IN ({placeholders})"
    params = ids[:]
    if chat_id is not None:
        sql += " AND m.chat_id=?"
        params.append(chat_id)
    with get_connection() as c:
        return c.execute(sql, params).fetchall()


def increment_stats(user_id, media_type=None, has_link=False):
    fields = ["message_count=message_count+1"]
    mapping = {"photo": "photo_count", "video": "video_count", "sticker": "sticker_count", "gif": "gif_count", "audio": "audio_count", "file": "file_count"}
    if media_type in mapping:
        fields.append(mapping[media_type] + "=" + mapping[media_type] + "+1")
    if has_link:
        fields.append("link_count=link_count+1")
    with get_connection() as c:
        c.execute(f"UPDATE private_chats SET {','.join(fields)},last_seen=? WHERE user_id=?", (_now(), user_id))
        c.commit()


def list_private_chats(include_bots=False):
    sql = "SELECT * FROM private_chats"
    if not include_bots:
        sql += " WHERE is_bot=0 AND is_deleted_user=0"
    sql += " ORDER BY last_seen DESC, archived ASC, display_name COLLATE NOCASE ASC"
    with get_connection() as c:
        return c.execute(sql).fetchall()


def get_private_chat(user_id):
    with get_connection() as c:
        return c.execute("SELECT * FROM private_chats WHERE user_id=?", (user_id,)).fetchone()


def list_messages(user_id, limit=30, offset=0):
    with get_connection() as c:
        return c.execute("SELECT * FROM messages WHERE user_id=? ORDER BY message_date ASC LIMIT ? OFFSET ?", (user_id, limit, offset)).fetchall()


def search_messages(user_id, text):
    with get_connection() as c:
        return c.execute("SELECT * FROM messages WHERE user_id=? AND text LIKE ? ORDER BY message_date DESC LIMIT 50", (user_id, f"%{text}%")).fetchall()


def mark_important(message_id):
    with get_connection() as c:
        c.execute("INSERT OR IGNORE INTO important_messages(message_id) VALUES(?)", (message_id,))
        c.commit()


def important_messages():
    with get_connection() as c:
        return c.execute("SELECT m.* FROM messages m JOIN important_messages i ON i.message_id=m.id ORDER BY i.created_at DESC").fetchall()


def ensure_private_contact(user_id, username=None, display_name=None, is_bot=False, is_deleted_user=False):
    upsert_private_chat(user_id, username, display_name, is_bot=is_bot, is_deleted_user=is_deleted_user)


def broadcast_targets():
    with get_connection() as c:
        return c.execute(
            '''SELECT p.* FROM private_chats p
               LEFT JOIN broadcast_exclusions b ON b.user_id=p.user_id
               WHERE p.broadcast_allowed=1
                 AND p.is_bot=0
                 AND p.is_deleted_user=0
                 AND b.user_id IS NULL
               ORDER BY p.display_name COLLATE NOCASE ASC'''
        ).fetchall()


def set_broadcast_allowed(user_id, allowed):
    with get_connection() as c:
        c.execute("UPDATE private_chats SET broadcast_allowed=? WHERE user_id=?", (int(allowed), user_id))
        c.commit()


def set_broadcast_exclusion(user_id, username=None, display_name=None):
    with get_connection() as c:
        c.execute("INSERT OR REPLACE INTO broadcast_exclusions(user_id,username,display_name) VALUES(?,?,?)", (user_id, username, display_name))
        c.commit()
        c.execute("UPDATE private_chats SET broadcast_allowed=0 WHERE user_id=?", (user_id,))
        c.commit()


def remove_broadcast_exclusion(user_id):
    with get_connection() as c:
        c.execute("DELETE FROM broadcast_exclusions WHERE user_id=?", (user_id,))
        c.execute("UPDATE private_chats SET broadcast_allowed=1 WHERE user_id=?", (user_id,))
        c.commit()


def list_broadcast_exclusions():
    with get_connection() as c:
        return c.execute("SELECT * FROM broadcast_exclusions ORDER BY created_at DESC").fetchall()


def list_broadcast_logs(limit=30):
    with get_connection() as c:
        return c.execute("SELECT * FROM broadcast_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def add_broadcast_log(text,total,sent,failed,started,finished,status="completed"):
    with get_connection() as c:
        c.execute("INSERT INTO broadcast_logs(text,total_targets,sent_count,failed_count,started_at,finished_at,status) VALUES(?,?,?,?,?,?,?)", (text,total,sent,failed,started,finished,status))
        c.commit()


def list_scheduled_broadcasts():
    with get_connection() as c:
        return c.execute("SELECT * FROM scheduled_broadcasts ORDER BY run_at ASC").fetchall()


def add_allowed_user(user_id, username=None, display_name=None, access_until=None):
    with get_global_connection() as c:
        c.execute("INSERT OR REPLACE INTO allowed_users(user_id,username,display_name,status,access_until) VALUES(?,?,?,?,?)", (user_id,username,display_name,"active",access_until))
        c.commit()


def remove_allowed_user(user_id):
    with get_global_connection() as c:
        c.execute("DELETE FROM allowed_users WHERE user_id=?", (user_id,))
        c.commit()


def get_allowed_user(user_id):
    with get_global_connection() as c:
        return c.execute("SELECT * FROM allowed_users WHERE user_id=?", (user_id,)).fetchone()


def get_allowed_users():
    with get_global_connection() as c:
        return c.execute("SELECT * FROM allowed_users ORDER BY created_at DESC").fetchall()


def ensure_feature_permissions(user_id):
    with get_global_connection() as c:
        for key, _ in FEATURES:
            c.execute("INSERT OR IGNORE INTO feature_permissions(user_id,feature_key,enabled) VALUES(?,?,1)", (user_id, key))
        c.commit()


def get_feature_permissions(user_id):
    ensure_feature_permissions(user_id)
    with get_global_connection() as c:
        return {r["feature_key"]: bool(r["enabled"]) for r in c.execute("SELECT feature_key,enabled FROM feature_permissions WHERE user_id=?", (user_id,)).fetchall()}


def set_feature_permission(user_id,key,enabled):
    with get_global_connection() as c:
        c.execute("INSERT OR REPLACE INTO feature_permissions(user_id,feature_key,enabled,updated_at) VALUES(?,?,?,?)", (user_id,key,int(enabled),_now()))
        c.commit()


def set_all_feature_permissions(user_id,enabled):
    with get_global_connection() as c:
        for key,_ in FEATURES:
            c.execute("INSERT OR REPLACE INTO feature_permissions(user_id,feature_key,enabled,updated_at) VALUES(?,?,?,?)", (user_id,key,int(enabled),_now()))
        c.commit()


def update_allowed_status(user_id,status,suspended_until=None):
    with get_global_connection() as c:
        c.execute("UPDATE allowed_users SET status=?,suspended_until=? WHERE user_id=?",(status,suspended_until,user_id))
        c.commit()


def get_recent_edits(user_id=None, limit=50):
    with get_connection() as c:
        if user_id is None:
            return c.execute("SELECT e.*, p.display_name, p.username FROM message_edit_history e LEFT JOIN private_chats p ON p.user_id=e.user_id ORDER BY e.id DESC LIMIT ?", (limit,)).fetchall()
        return c.execute("SELECT e.*, p.display_name, p.username FROM message_edit_history e LEFT JOIN private_chats p ON p.user_id=e.user_id WHERE e.user_id=? ORDER BY e.id DESC LIMIT ?", (user_id,limit)).fetchall()


def count_messages_for_chat(user_id):
    with get_connection() as c:
        row = c.execute("SELECT COUNT(*) AS n FROM messages WHERE user_id=?", (user_id,)).fetchone()
        return int(row["n"] or 0)


def find_exact_message(user_id, text):
    with get_connection() as c:
        return c.execute("SELECT * FROM messages WHERE user_id=? AND text=? ORDER BY message_date DESC LIMIT 20", (user_id, text)).fetchall()


def is_broadcast_excluded(user_id):
    with get_connection() as c:
        return c.execute("SELECT 1 FROM broadcast_exclusions WHERE user_id=?", (user_id,)).fetchone() is not None



def get_user_session(bot_user_id):
    with get_global_connection() as c:
        return c.execute("SELECT * FROM user_sessions WHERE bot_user_id=?", (bot_user_id,)).fetchone()


def save_user_session(bot_user_id, session_path, telegram_user_id=None, phone_hint=None, status="active"):
    with get_global_connection() as c:
        c.execute(
            "INSERT OR REPLACE INTO user_sessions(bot_user_id,session_path,telegram_user_id,phone_hint,status,updated_at) VALUES(?,?,?,?,?,?)",
            (bot_user_id, session_path, telegram_user_id, phone_hint, status, _now()),
        )
        c.commit()


def delete_user_session(bot_user_id):
    with get_global_connection() as c:
        c.execute("DELETE FROM user_sessions WHERE bot_user_id=?", (bot_user_id,))
        c.commit()


def list_user_sessions():
    with get_global_connection() as c:
        return c.execute("SELECT * FROM user_sessions ORDER BY created_at ASC").fetchall()

def expire_access_users():
    now = _now()
    with get_global_connection() as c:
        c.execute("UPDATE allowed_users SET status='banned' WHERE access_until IS NOT NULL AND access_until < ?", (now,))
        c.execute("UPDATE allowed_users SET status='active',suspended_until=NULL WHERE status='suspended' AND suspended_until IS NOT NULL AND suspended_until < ?", (now,))
        c.commit()


def is_feature_enabled(user_id, feature_key):
    return bool(get_feature_permissions(user_id).get(feature_key, True))



def private_chats_page(page=0, per_page=10):
    page = max(0, int(page))
    offset = page * per_page
    with get_connection() as c:
        total = c.execute("SELECT COUNT(*) AS n FROM private_chats WHERE is_bot=0 AND is_deleted_user=0").fetchone()["n"]
        rows = c.execute(
            "SELECT * FROM private_chats WHERE is_bot=0 AND is_deleted_user=0 ORDER BY last_seen DESC, archived ASC, display_name COLLATE NOCASE ASC LIMIT ? OFFSET ?",
            (per_page, offset),
        ).fetchall()
    return rows, int(total)


def search_private_chats(query, limit=25):
    q = str(query or "").strip()
    if not q:
        return list_private_chats()[:limit]
    like = f"%{q}%"
    with get_connection() as c:
        return c.execute(
            """SELECT * FROM private_chats
               WHERE is_bot=0 AND is_deleted_user=0
                 AND (display_name LIKE ? OR username LIKE ? OR CAST(user_id AS TEXT) LIKE ?)
               ORDER BY last_seen DESC, display_name COLLATE NOCASE ASC LIMIT ?""",
            (like, like.lstrip("@"), like, limit),
        ).fetchall()


def add_ai_log(source, user_id, display_name, username, chat_id, chat_type, prompt, answer):
    with get_connection() as c:
        c.execute(
            """INSERT INTO ai_logs(source,user_id,display_name,username,chat_id,chat_type,prompt,answer)
               VALUES(?,?,?,?,?,?,?,?)""",
            (source, user_id, display_name, username, chat_id, chat_type, prompt, answer),
        )
        c.commit()


def list_ai_logs(limit=30):
    with get_connection() as c:
        return c.execute("SELECT * FROM ai_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

def add_bot_access_log(user_id, display_name=None, username=None, status="denied"):
    with get_global_connection() as c:
        c.execute(
            "INSERT INTO bot_access_log(user_id,display_name,username,status) VALUES(?,?,?,?)",
            (user_id, display_name, username, status),
        )
        c.commit()


def register_denied_access(user_id):
    """Track unauthorized /start attempts and keep user/owner notifications one-time."""
    now = _now()
    now_dt = datetime.fromisoformat(now)
    with get_global_connection() as c:
        row = c.execute("SELECT * FROM bot_access_attempts WHERE user_id=?", (user_id,)).fetchone()

        if row and row["last_attempt_at"]:
            try:
                last_dt = datetime.fromisoformat(row["last_attempt_at"])
                elapsed = (now_dt - last_dt).total_seconds()
            except Exception:
                elapsed = 999999
        else:
            elapsed = 999999

        if row and elapsed < 5:
            attempts = int(row["attempts"] or 0) + 1
        else:
            attempts = 1

        restricted = 1 if attempts >= 3 else 0
        notified = int(row["notified"] or 0) if row else 0
        user_notified = int(row["user_notified"] or 0) if row else 0

        c.execute(
            "INSERT INTO bot_access_attempts(user_id,attempts,notified,user_notified,restricted,updated_at,last_attempt_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET attempts=excluded.attempts, notified=excluded.notified, user_notified=excluded.user_notified, restricted=excluded.restricted, updated_at=excluded.updated_at, last_attempt_at=excluded.last_attempt_at",
            (user_id, attempts, notified, user_notified, restricted, now, now),
        )
        c.commit()

    return {
        "attempts": attempts,
        "notify_owner": user_notified == 0,
        "notify_user": user_notified == 0,
        "restricted": attempts >= 3,
        "ban": False,
    }

def mark_denied_access_user_notified(user_id):
    with get_global_connection() as c:
        c.execute("UPDATE bot_access_attempts SET user_notified=1, updated_at=? WHERE user_id=?", (_now(), user_id))
        c.commit()

def mark_denied_access_notified(user_id):
    with get_global_connection() as c:
        c.execute("UPDATE bot_access_attempts SET notified=1, updated_at=? WHERE user_id=?", (_now(), user_id))
        c.commit()


def reset_access_attempts(user_id):
    with get_global_connection() as c:
        c.execute("DELETE FROM bot_access_attempts WHERE user_id=?", (user_id,))
        c.commit()


def list_banned_users(limit=100):
    with get_global_connection() as c:
        return c.execute("SELECT * FROM allowed_users WHERE status='banned' ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()


def list_bot_access_logs(limit=50, offset=0):
    with get_global_connection() as c:
        return c.execute(
            "SELECT * FROM bot_access_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()


def count_bot_access_logs():
    with get_global_connection() as c:
        row = c.execute("SELECT COUNT(*) AS n FROM bot_access_log").fetchone()
        return int(row["n"] if row else 0)


def list_recent_incoming_messages(user_id, limit=100):
    with get_connection() as c:
        return c.execute(
            "SELECT m.*, p.display_name, p.username FROM messages m LEFT JOIN private_chats p ON p.user_id=m.user_id WHERE m.user_id=? AND m.direction='incoming' AND m.deleted_at IS NULL ORDER BY m.telegram_message_id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def message_marked_deleted(telegram_message_id, chat_id, direction="incoming"):
    with get_connection() as c:
        row = c.execute(
            "SELECT id FROM messages WHERE telegram_message_id=? AND chat_id=? AND direction=? AND deleted_at IS NULL LIMIT 1",
            (telegram_message_id, chat_id, direction),
        ).fetchone()
        if not row:
            return False
        c.execute(
            "UPDATE messages SET deleted_at=? WHERE id=?",
            (_now(), row["id"]),
        )
        c.commit()
        return True


def add_scheduled_broadcast(text, run_at):
    with get_connection() as c:
        cur = c.execute("INSERT INTO scheduled_broadcasts(text,run_at,status) VALUES(?,?,?)", (text, run_at, "scheduled"))
        c.commit()
        return cur.lastrowid


def cancel_scheduled_broadcast(item_id):
    with get_connection() as c:
        cur = c.execute("UPDATE scheduled_broadcasts SET status='cancelled' WHERE id=? AND status='scheduled'", (item_id,))
        c.commit()
        return cur.rowcount > 0


def clear_bot_access_logs():
    with get_global_connection() as c:
        c.execute("DELETE FROM bot_access_log")
        c.commit()


def clear_logs(table):
    if table not in {"operation_log", "security_log"}:
        return False
    with get_connection() as c:
        c.execute(f"DELETE FROM {table}")
        c.commit()
    return True
