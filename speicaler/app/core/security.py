import os
import re
from pathlib import Path


def validate_runtime_security(bot_token: str, api_id: str, api_hash: str, admin_id: str) -> None:
    """Fail closed on missing/obviously malformed production secrets."""
    if not bot_token or ':' not in bot_token:
        raise RuntimeError('BOT_TOKEN غير مضبوط أو غير صالح')
    if not api_id or not api_id.isdigit():
        raise RuntimeError('API_ID غير مضبوط أو غير رقمي')
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,64}', api_hash or ''):
        raise RuntimeError('API_HASH غير مضبوط أو غير صالح')
    if not admin_id or not admin_id.isdigit():
        raise RuntimeError('OWNER_ID/ADMIN_ID غير مضبوط')


def security_checklist(root: Path) -> list[str]:
    checks = []
    checks.append('Secrets are loaded from .env and never from source files')
    checks.append('Telegram session files are excluded from Git')
    checks.append('Only approved bot users can reach protected handlers')
    checks.append('Owner ID is required at startup')
    checks.append('Use a newly regenerated BotFather token after any compromise')
    return checks
