import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import profile_db_path, BACKUP_DIR, MEDIA_DIR, get_connection


def _rows(query, params=()):
    with get_connection() as c:
        return [dict(row) for row in c.execute(query, params).fetchall()]


def create_full_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"special_backup_{stamp}.zip"
    snapshot = BACKUP_DIR / f"special_snapshot_{stamp}.json"

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "private_chats": _rows("SELECT * FROM private_chats ORDER BY last_seen DESC"),
        "messages": _rows("SELECT * FROM messages ORDER BY id ASC"),
        "important_messages": _rows("SELECT * FROM important_messages ORDER BY id ASC"),
        "muted_users": _rows("SELECT * FROM muted_users ORDER BY created_at DESC"),
        "broadcast_exclusions": _rows("SELECT * FROM broadcast_exclusions ORDER BY created_at DESC"),
        "broadcast_logs": _rows("SELECT * FROM broadcast_logs ORDER BY id ASC"),
        "settings": _rows("SELECT * FROM settings ORDER BY key ASC"),
        "operation_log": _rows("SELECT * FROM operation_log ORDER BY id ASC"),
        "security_log": _rows("SELECT * FROM security_log ORDER BY id ASC"),
    }
    snapshot.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(profile_db_path(), arcname="special.db")
        z.write(snapshot, arcname="snapshot.json")
        if MEDIA_DIR.exists():
            for path in MEDIA_DIR.rglob("*"):
                if path.is_file():
                    z.write(path, arcname=str(Path("media") / path.relative_to(MEDIA_DIR)))
    snapshot.unlink(missing_ok=True)
    return target


def create_chat_backup(user_id: int) -> Path | None:
    row = None
    with get_connection() as c:
        row = c.execute("SELECT * FROM private_chats WHERE user_id=?", (user_id,)).fetchone()
        messages = [dict(x) for x in c.execute("SELECT * FROM messages WHERE user_id=? ORDER BY message_date ASC", (user_id,)).fetchall()]
    if not row:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"chat_{user_id}_{stamp}.txt"
    lines = [
        f"Special conversation backup",
        f"User ID: {user_id}",
        f"Name: {row['display_name'] or ''}",
        f"Username: @{row['username']}" if row['username'] else "Username: لا يوجد يوزر",
        "",
    ]
    for m in messages:
        direction = "IN" if m["direction"] == "incoming" else "OUT"
        body = m["text"] or f"[{m['media_type'] or 'media'}]"
        lines.append(f"[{m['message_date'] or ''}] {direction}: {body}")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
