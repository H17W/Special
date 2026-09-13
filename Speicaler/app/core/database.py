from __future__ import annotations

import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .config import settings


class DB:
    def __init__(self, path=None):
        self.path = str(path or settings.db_path)
        self.lock = threading.RLock()

        parent = Path(self.path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

        self._init()

    @contextmanager
    def conn(self):
        with self.lock:
            c = sqlite3.connect(
                self.path,
                timeout=30,
                check_same_thread=False,
            )
            c.row_factory = sqlite3.Row

            try:
                c.execute("PRAGMA busy_timeout=30000")
                c.execute("PRAGMA foreign_keys=ON")
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise
            finally:
                c.close()

    def one(self, q, p=()):
        with self.conn() as c:
            return c.execute(q, p).fetchone()

    def all(self, q, p=()):
        with self.conn() as c:
            return c.execute(q, p).fetchall()

    def run(self, q, p=()):
        with self.conn() as c:
            return c.execute(q, p).rowcount

    # ---------------------------------------------------------
    # Schema helpers
    # ---------------------------------------------------------

    def _table_exists(self, c, table):
        row = c.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name=?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        return row is not None

    def _columns(self, c, table):
        if not self._table_exists(c, table):
            return set()

        return {
            str(row["name"])
            for row in c.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()
        }

    def _column_exists(self, c, table, column):
        return column in self._columns(c, table)

    def _rename_table(self, c, old, new):
        if self._table_exists(c, old) and not self._table_exists(c, new):
            c.execute(f'ALTER TABLE "{old}" RENAME TO "{new}"')

    # ---------------------------------------------------------
    # Initialization / migrations
    # ---------------------------------------------------------

    def _init(self):
        with self.conn() as c:
            c.execute("PRAGMA journal_mode=WAL")

            # -------------------------------------------------
            # Core users
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS users(
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    expires_at INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )

            c.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_users_status
                ON users(status)
                """
            )

            # -------------------------------------------------
            # Access requests
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS access_requests(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT,
                    created_at INTEGER NOT NULL,
                    handled_at INTEGER
                )
                """
            )

            c.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_access_status
                ON access_requests(status, created_at)
                """
            )

            # -------------------------------------------------
            # Restrictions
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS restrictions(
                    user_id INTEGER PRIMARY KEY,
                    until_at INTEGER,
                    permanent INTEGER NOT NULL DEFAULT 0,
                    reason TEXT,
                    updated_at INTEGER NOT NULL
                )
                """
            )

            # -------------------------------------------------
            # Settings
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS settings(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            # -------------------------------------------------
            # Feature permissions
            #
            # Old DB used:
            # feature_key
            #
            # New code uses:
            # feature
            # -------------------------------------------------

            if self._table_exists(c, "feature_permissions"):
                cols = self._columns(c, "feature_permissions")

                if "feature" not in cols and "feature_key" in cols:
                    c.execute(
                        """
                        ALTER TABLE feature_permissions
                        RENAME TO feature_permissions_legacy
                        """
                    )

                    c.execute(
                        """
                        CREATE TABLE feature_permissions(
                            user_id INTEGER NOT NULL,
                            feature TEXT NOT NULL,
                            enabled INTEGER NOT NULL DEFAULT 1,
                            PRIMARY KEY(user_id, feature)
                        )
                        """
                    )

                    c.execute(
                        """
                        INSERT OR IGNORE INTO feature_permissions
                            (user_id, feature, enabled)
                        SELECT
                            user_id,
                            feature_key,
                            enabled
                        FROM feature_permissions_legacy
                        """
                    )

                    c.execute(
                        """
                        DROP TABLE feature_permissions_legacy
                        """
                    )
            else:
                c.execute(
                    """
                    CREATE TABLE feature_permissions(
                        user_id INTEGER NOT NULL,
                        feature TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY(user_id, feature)
                    )
                    """
                )

            # -------------------------------------------------
            # Private exceptions
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS private_exceptions(
                    user_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    PRIMARY KEY(user_id, target_id)
                )
                """
            )

            # -------------------------------------------------
            # Muted users
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS muted_users(
                    target_id INTEGER PRIMARY KEY,
                    username TEXT,
                    created_at INTEGER NOT NULL
                )
                """
            )

            # -------------------------------------------------
            # /start abuse
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS start_abuse(
                    user_id INTEGER PRIMARY KEY,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_at INTEGER NOT NULL DEFAULT 0,
                    notify_at INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            # -------------------------------------------------
            # Temporary access links
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS temp_links(
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    grant_seconds INTEGER NOT NULL DEFAULT 86400,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    uses INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            # -------------------------------------------------
            # Delete sessions
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS delete_sessions(
                    user_id INTEGER PRIMARY KEY,
                    target_chat_id INTEGER,
                    start_message_id INTEGER,
                    updated_at INTEGER NOT NULL
                )
                """
            )

            # -------------------------------------------------
            # Keyboard sessions
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS keyboard_sessions(
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(chat_id, message_id)
                )
                """
            )

            # -------------------------------------------------
            # Keyboard abuse
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS keyboard_abuse(
                    user_id INTEGER PRIMARY KEY,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                )
                """
            )

            # -------------------------------------------------
            # Audio jobs
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS audio_jobs(
                    user_id INTEGER PRIMARY KEY,
                    path TEXT,
                    title TEXT,
                    artist TEXT,
                    cover TEXT,
                    updated_at INTEGER NOT NULL
                )
                """
            )

            # -------------------------------------------------
            # Message archive
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS message_archive(
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    sender_id INTEGER,
                    sender_name TEXT,
                    sender_username TEXT,
                    kind TEXT,
                    text TEXT,
                    media_type TEXT,
                    media_path TEXT,
                    created_at INTEGER NOT NULL,
                    edited_at INTEGER,
                    deleted_at INTEGER,
                    PRIMARY KEY(chat_id, message_id)
                )
                """
            )

            c.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_archive_chat_time
                ON message_archive(chat_id, created_at, message_id)
                """
            )

            c.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_archive_sender
                ON message_archive(sender_id, created_at)
                """
            )

            # -------------------------------------------------
            # Private chats
            #
            # Older DB had:
            # user_id, username, display_name, last_seen...
            #
            # New system uses:
            # chat_id, peer_id, peer_name, peer_username...
            # -------------------------------------------------

            if self._table_exists(c, "private_chats"):
                cols = self._columns(c, "private_chats")

                if "chat_id" not in cols:
                    c.execute(
                        """
                        ALTER TABLE private_chats
                        RENAME TO private_chats_legacy
                        """
                    )

                    c.execute(
                        """
                        CREATE TABLE private_chats(
                            chat_id INTEGER PRIMARY KEY,
                            peer_id INTEGER,
                            peer_name TEXT,
                            peer_username TEXT,
                            last_message_at INTEGER,
                            imported_at INTEGER
                        )
                        """
                    )

                    legacy_cols = self._columns(
                        c,
                        "private_chats_legacy",
                    )

                    if "user_id" in legacy_cols:
                        username_expr = (
                            "username"
                            if "username" in legacy_cols
                            else "NULL"
                        )

                        name_expr = (
                            "display_name"
                            if "display_name" in legacy_cols
                            else "NULL"
                        )

                        last_expr = (
                            "last_seen"
                            if "last_seen" in legacy_cols
                            else "NULL"
                        )

                        c.execute(
                            f"""
                            INSERT OR IGNORE INTO private_chats(
                                chat_id,
                                peer_id,
                                peer_name,
                                peer_username,
                                last_message_at,
                                imported_at
                            )
                            SELECT
                                user_id,
                                user_id,
                                {name_expr},
                                {username_expr},
                                {last_expr},
                                strftime('%s','now')
                            FROM private_chats_legacy
                            """
                        )

                    c.execute(
                        """
                        DROP TABLE private_chats_legacy
                        """
                    )
            else:
                c.execute(
                    """
                    CREATE TABLE private_chats(
                        chat_id INTEGER PRIMARY KEY,
                        peer_id INTEGER,
                        peer_name TEXT,
                        peer_username TEXT,
                        last_message_at INTEGER,
                        imported_at INTEGER
                    )
                    """
                )

            # -------------------------------------------------
            # Operation log
            #
            # Older DB:
            # id, event_type, description, created_at
            #
            # New DB:
            # id, user_id, action, detail, created_at
            #
            # Migrate instead of trying to create indexes on
            # missing columns.
            # -------------------------------------------------

            if self._table_exists(c, "operation_log"):
                cols = self._columns(c, "operation_log")

                if "action" not in cols:
                    c.execute(
                        """
                        ALTER TABLE operation_log
                        RENAME TO operation_log_legacy
                        """
                    )

                    c.execute(
                        """
                        CREATE TABLE operation_log(
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            action TEXT,
                            detail TEXT,
                            created_at INTEGER NOT NULL
                        )
                        """
                    )

                    legacy_cols = self._columns(
                        c,
                        "operation_log_legacy",
                    )

                    event_expr = (
                        "event_type"
                        if "event_type" in legacy_cols
                        else "NULL"
                    )

                    detail_expr = (
                        "description"
                        if "description" in legacy_cols
                        else "NULL"
                    )

                    created_expr = (
                        "created_at"
                        if "created_at" in legacy_cols
                        else "strftime('%s','now')"
                    )

                    c.execute(
                        f"""
                        INSERT INTO operation_log(
                            id,
                            user_id,
                            action,
                            detail,
                            created_at
                        )
                        SELECT
                            id,
                            NULL,
                            {event_expr},
                            {detail_expr},
                            CAST({created_expr} AS INTEGER)
                        FROM operation_log_legacy
                        """
                    )

                    c.execute(
                        """
                        DROP TABLE operation_log_legacy
                        """
                    )

            else:
                c.execute(
                    """
                    CREATE TABLE operation_log(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        action TEXT,
                        detail TEXT,
                        created_at INTEGER NOT NULL
                    )
                    """
                )

            c.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ops_user_time
                ON operation_log(user_id, created_at DESC)
                """
            )

            c.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ops_action_time
                ON operation_log(action, created_at DESC)
                """
            )

            # -------------------------------------------------
            # Cleanup policy
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS cleanup_policy(
                    category TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    retention_seconds INTEGER NOT NULL DEFAULT 2592000,
                    custom_seconds INTEGER
                )
                """
            )

            # -------------------------------------------------
            # Broadcast jobs
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS broadcast_jobs(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER,
                    status TEXT,
                    created_at INTEGER,
                    started_at INTEGER,
                    finished_at INTEGER,
                    total INTEGER,
                    sent INTEGER,
                    failed INTEGER,
                    text TEXT
                )
                """
            )

            # -------------------------------------------------
            # Storage
            # -------------------------------------------------

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_items(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    kind TEXT,
                    path TEXT,
                    caption TEXT,
                    category TEXT,
                    created_at INTEGER NOT NULL
                )
                """
            )

            c.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_storage_kind_time
                ON storage_items(kind, created_at DESC)
                """
            )

            c.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_storage_user_time
                ON storage_items(user_id, created_at DESC)
                """
            )

            # -------------------------------------------------
            # Keep useful indexes for existing archive tables
            # -------------------------------------------------

            if self._table_exists(c, "messages"):
                msg_cols = self._columns(c, "messages")

                if "user_id" in msg_cols and "created_at" in msg_cols:
                    c.execute(
                        """
                        CREATE INDEX IF NOT EXISTS
                        idx_messages_user_time
                        ON messages(user_id, created_at DESC)
                        """
                    )

                if "chat_id" in msg_cols and "created_at" in msg_cols:
                    c.execute(
                        """
                        CREATE INDEX IF NOT EXISTS
                        idx_messages_chat_time
                        ON messages(chat_id, created_at DESC)
                        """
                    )

            # -------------------------------------------------
            # Default cleanup policies
            # -------------------------------------------------

            defaults = {
                "operations": 604800,
                "private_log": 2592000,
                "access": 2592000,
                "broadcast": 2592000,
                "storage": 2592000,
            }

            for category, seconds in defaults.items():
                c.execute(
                    """
                    INSERT OR IGNORE INTO cleanup_policy(
                        category,
                        enabled,
                        retention_seconds
                    )
                    VALUES(?,1,?)
                    """,
                    (category, seconds),
                )

    # ---------------------------------------------------------
    # Logging
    # ---------------------------------------------------------

    def log(self, uid, action, detail=""):
        self.run(
            """
            INSERT INTO operation_log(
                user_id,
                action,
                detail,
                created_at
            )
            VALUES(?,?,?,?)
            """,
            (
                uid,
                action,
                detail,
                int(time.time()),
            ),
        )

    # ---------------------------------------------------------
    # Users
    # ---------------------------------------------------------

    def upsert_user(
        self,
        uid,
        username="",
        first_name="",
    ):
        now = int(time.time())

        self.run(
            """
            INSERT INTO users(
                id,
                username,
                first_name,
                created_at,
                updated_at
            )
            VALUES(?,?,?,?,?)
            ON CONFLICT(id)
            DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                username or "",
                first_name or "",
                now,
                now,
            ),
        )

    def user(self, uid):
        return self.one(
            "SELECT * FROM users WHERE id=?",
            (uid,),
        )

    def access_active(self, uid):
        if uid == settings.owner_id:
            return True

        r = self.user(uid)

        if not r:
            return False

        if r["status"] != "active":
            return False

        expires_at = r["expires_at"]

        return (
            expires_at is None
            or int(expires_at) > int(time.time())
        )

    # ---------------------------------------------------------
    # Access requests
    # ---------------------------------------------------------

    def request_access(self, uid):
        r = self.one(
            """
            SELECT id
            FROM access_requests
            WHERE user_id=? AND status='pending'
            ORDER BY id DESC
            LIMIT 1
            """,
            (uid,),
        )

        if r:
            return int(r["id"]), False

        now = int(time.time())

        with self.conn() as c:
            cur = c.execute(
                """
                INSERT INTO access_requests(
                    user_id,
                    created_at
                )
                VALUES(?,?)
                """,
                (uid, now),
            )

            return int(cur.lastrowid), True

    def pending_requests(
        self,
        limit=25,
        offset=0,
    ):
        return self.all(
            """
            SELECT *
            FROM access_requests
            WHERE status='pending'
            ORDER BY created_at
            LIMIT ? OFFSET ?
            """,
            (
                limit,
                offset,
            ),
        )

    def decide_request(
        self,
        rid,
        uid,
        accept,
        expires_at=None,
        reason=None,
    ):
        now = int(time.time())
        status = "accepted" if accept else "rejected"

        with self.conn() as c:
            c.execute(
                """
                UPDATE access_requests
                SET
                    status=?,
                    reason=?,
                    handled_at=?
                WHERE id=?
                """,
                (
                    status,
                    reason,
                    now,
                    rid,
                ),
            )

            c.execute(
                """
                UPDATE users
                SET
                    status=?,
                    expires_at=?,
                    updated_at=?
                WHERE id=?
                """,
                (
                    "active" if accept else "rejected",
                    expires_at if accept else None,
                    now,
                    uid,
                ),
            )

    # ---------------------------------------------------------
    # Restrictions
    # ---------------------------------------------------------

    def restrict(
        self,
        uid,
        seconds=None,
        permanent=False,
        reason="",
    ):
        until = (
            None
            if permanent
            else int(time.time()) + int(seconds or 0)
        )

        self.run(
            """
            INSERT INTO restrictions(
                user_id,
                until_at,
                permanent,
                reason,
                updated_at
            )
            VALUES(?,?,?,?,?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                until_at=excluded.until_at,
                permanent=excluded.permanent,
                reason=excluded.reason,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                until,
                int(permanent),
                reason,
                int(time.time()),
            ),
        )

    def unrestricted(self, uid):
        r = self.one(
            """
            SELECT *
            FROM restrictions
            WHERE user_id=?
            """,
            (uid,),
        )

        if not r:
            return True

        if r["permanent"]:
            return False

        if (
            r["until_at"]
            and r["until_at"] > int(time.time())
        ):
            return False

        self.run(
            "DELETE FROM restrictions WHERE user_id=?",
            (uid,),
        )

        return True

    def remaining_restriction(self, uid):
        r = self.one(
            """
            SELECT *
            FROM restrictions
            WHERE user_id=?
            """,
            (uid,),
        )

        if not r:
            return 0

        if r["permanent"]:
            return -1

        return max(
            0,
            int(r["until_at"] or 0) - int(time.time()),
        )

    # ---------------------------------------------------------
    # Settings
    # ---------------------------------------------------------

    def set_setting(self, key, value):
        self.run(
            """
            INSERT INTO settings(key,value)
            VALUES(?,?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
            """,
            (
                key,
                str(value),
            ),
        )

    def get_setting(self, key, default="0"):
        r = self.one(
            """
            SELECT value
            FROM settings
            WHERE key=?
            """,
            (key,),
        )

        return r["value"] if r else default

    # ---------------------------------------------------------
    # Feature permissions
    # ---------------------------------------------------------

    def feature(self, uid, key):
        r = self.one(
            """
            SELECT enabled
            FROM feature_permissions
            WHERE user_id=? AND feature=?
            """,
            (
                uid,
                key,
            ),
        )

        return True if not r else bool(r["enabled"])

    def set_feature(self, uid, key, enabled):
        self.run(
            """
            INSERT INTO feature_permissions(
                user_id,
                feature,
                enabled
            )
            VALUES(?,?,?)
            ON CONFLICT(user_id,feature)
            DO UPDATE SET
                enabled=excluded.enabled
            """,
            (
                uid,
                key,
                int(enabled),
            ),
        )

    # ---------------------------------------------------------
    # Private exceptions
    # ---------------------------------------------------------

    def add_private_exception(self, uid, target):
        self.run(
            """
            INSERT OR IGNORE INTO private_exceptions(
                user_id,
                target_id
            )
            VALUES(?,?)
            """,
            (
                uid,
                target,
            ),
        )

    def del_private_exception(self, uid, target):
        self.run(
            """
            DELETE FROM private_exceptions
            WHERE user_id=? AND target_id=?
            """,
            (
                uid,
                target,
            ),
        )

    def private_exception(self, uid, target):
        return bool(
            self.one(
                """
                SELECT 1
                FROM private_exceptions
                WHERE user_id=? AND target_id=?
                """,
                (
                    uid,
                    target,
                ),
            )
        )

    # ---------------------------------------------------------
    # Mute
    # ---------------------------------------------------------

    def mute(self, target, username=""):
        self.run(
            """
            INSERT OR REPLACE INTO muted_users(
                target_id,
                username,
                created_at
            )
            VALUES(?,?,?)
            """,
            (
                target,
                username,
                int(time.time()),
            ),
        )

    def unmute(self, target):
        self.run(
            """
            DELETE FROM muted_users
            WHERE target_id=?
            """,
            (target,),
        )

    def muted(self, target):
        return bool(
            self.one(
                """
                SELECT 1
                FROM muted_users
                WHERE target_id=?
                """,
                (target,),
            )
        )

    # ---------------------------------------------------------
    # Temporary links
    # ---------------------------------------------------------

    def create_link(
        self,
        uid,
        seconds,
        max_uses=1,
        grant_seconds=86400,
    ):
        token = secrets.token_urlsafe(24)

        self.run(
            """
            INSERT INTO temp_links(
                token,
                user_id,
                expires_at,
                grant_seconds,
                max_uses,
                uses
            )
            VALUES(?,?,?,?,?,0)
            """,
            (
                token,
                uid,
                int(time.time()) + int(seconds),
                int(grant_seconds),
                int(max_uses),
            ),
        )

        return token

    def consume_link(
        self,
        token,
        requesting_user_id=None,
    ):
        r = self.one(
            """
            SELECT *
            FROM temp_links
            WHERE token=?
            """,
            (token,),
        )

        if not r:
            return None

        if int(r["expires_at"]) <= int(time.time()):
            return None

        if int(r["uses"]) >= int(r["max_uses"]):
            return None

        if (
            requesting_user_id is not None
            and int(r["user_id"]) != int(requesting_user_id)
        ):
            return None

        self.run(
            """
            UPDATE temp_links
            SET uses=uses+1
            WHERE token=?
            """,
            (token,),
        )

        return (
            int(r["user_id"]),
            int(r["grant_seconds"]),
        )

    # ---------------------------------------------------------
    # Delete sessions
    # ---------------------------------------------------------

    def set_delete_start(
        self,
        uid,
        chat,
        msg,
    ):
        self.run(
            """
            INSERT INTO delete_sessions(
                user_id,
                target_chat_id,
                start_message_id,
                updated_at
            )
            VALUES(?,?,?,?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                target_chat_id=excluded.target_chat_id,
                start_message_id=excluded.start_message_id,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                chat,
                msg,
                int(time.time()),
            ),
        )

    def delete_session(self, uid):
        return self.one(
            """
            SELECT *
            FROM delete_sessions
            WHERE user_id=?
            """,
            (uid,),
        )

    def clear_delete(self, uid):
        self.run(
            """
            DELETE FROM delete_sessions
            WHERE user_id=?
            """,
            (uid,),
        )

    # ---------------------------------------------------------
    # Keyboard abuse
    # ---------------------------------------------------------

    def keyboard_abuse(self, uid):
        r = self.one(
            """
            SELECT attempts, updated_at
            FROM keyboard_abuse
            WHERE user_id=?
            """,
            (uid,),
        )

        if not r:
            return 0

        if (
            int(time.time()) - int(r["updated_at"])
            > 3600
        ):
            self.run(
                """
                DELETE FROM keyboard_abuse
                WHERE user_id=?
                """,
                (uid,),
            )
            return 0

        return int(r["attempts"])

    def add_keyboard_abuse(self, uid):
        n = self.keyboard_abuse(uid) + 1

        self.run(
            """
            INSERT INTO keyboard_abuse(
                user_id,
                attempts,
                updated_at
            )
            VALUES(?,?,?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                attempts=excluded.attempts,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                n,
                int(time.time()),
            ),
        )

        return n

    # ---------------------------------------------------------
    # Statistics
    # ---------------------------------------------------------

    def stats(self):
        queries = {
            "users": """
                SELECT COUNT(*)
                FROM users
            """,
            "active": """
                SELECT COUNT(*)
                FROM users
                WHERE status='active'
            """,
            "requests": """
                SELECT COUNT(*)
                FROM access_requests
                WHERE status='pending'
            """,
            "muted": """
                SELECT COUNT(*)
                FROM muted_users
            """,
            "logs": """
                SELECT COUNT(*)
                FROM operation_log
            """,
            "messages": """
                SELECT COUNT(*)
                FROM message_archive
            """,
            "storage": """
                SELECT COUNT(*)
                FROM storage_items
            """,
            "broadcasts": """
                SELECT COUNT(*)
                FROM broadcast_jobs
            """,
        }

        return {
            key: self.one(query)[0]
            for key, query in queries.items()
        }

    # ---------------------------------------------------------
    # Expiration cleanup
    # ---------------------------------------------------------

    def cleanup_expired(self):
        now = int(time.time())

        self.run(
            """
            DELETE FROM temp_links
            WHERE expires_at<=?
            """,
            (now,),
        )

        self.run(
            """
            DELETE FROM restrictions
            WHERE permanent=0
              AND until_at IS NOT NULL
              AND until_at<=?
            """,
            (now,),
        )

        self.run(
            """
            UPDATE users
            SET status='expired'
            WHERE status='active'
              AND expires_at IS NOT NULL
              AND expires_at<=?
            """,
            (now,),
        )

    # ---------------------------------------------------------
    # Operation logs
    # ---------------------------------------------------------

    def logs(
        self,
        limit=25,
        offset=0,
        user_id=None,
        action=None,
    ):
        query = """
            SELECT *
            FROM operation_log
            WHERE 1=1
        """

        params = []

        if user_id is not None:
            query += " AND user_id=?"
            params.append(user_id)

        if action:
            query += " AND action=?"
            params.append(action)

        query += """
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """

        params.extend(
            [
                int(limit),
                int(offset),
            ]
        )

        return self.all(
            query,
            params,
        )

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------

    def cleanup_category(
        self,
        category,
        older_than,
    ):
        cutoff = int(time.time()) - int(older_than)

        mapping = {
            "operations": "operation_log",
            "private_log": "message_archive",
            "access": "access_requests",
            "broadcast": "broadcast_jobs",
            "storage": "storage_items",
        }

        table = mapping.get(category)

        if not table:
            return 0

        return self.run(
            f"""
            DELETE FROM "{table}"
            WHERE created_at<?
            """,
            (cutoff,),
        )

    def cleanup_counts(self):
        return {
            "operations": self.one(
                """
                SELECT COUNT(*)
                FROM operation_log
                """
            )[0],

            "private_log": self.one(
                """
                SELECT COUNT(*)
                FROM message_archive
                """
            )[0],

            "access": self.one(
                """
                SELECT COUNT(*)
                FROM access_requests
                """
            )[0],

            "broadcast": self.one(
                """
                SELECT COUNT(*)
                FROM broadcast_jobs
                """
            )[0],

            "storage": self.one(
                """
                SELECT COUNT(*)
                FROM storage_items
                """
            )[0],
        }


db = DB()
