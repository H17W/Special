import sqlite3
from pathlib import Path


DB_PATH = Path("special.db")


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS muted_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def mute_user(user_id: int, username: str | None, display_name: str | None):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO muted_users
            (user_id, username, display_name)
            VALUES (?, ?, ?)
            """,
            (user_id, username, display_name),
        )
        connection.commit()


def unmute_user(user_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM muted_users WHERE user_id = ?",
            (user_id,),
        )
        connection.commit()
        return cursor.rowcount > 0


def is_muted(user_id: int) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM muted_users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        return row is not None


def get_muted_user(user_id: int):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM muted_users WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def get_all_muted_users():
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM muted_users ORDER BY created_at DESC"
        ).fetchall()
