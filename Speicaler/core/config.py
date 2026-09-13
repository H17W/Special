from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
STORAGE = ROOT / 'storage'; STORAGE.mkdir(exist_ok=True)
BACKUPS = ROOT / 'backups'; BACKUPS.mkdir(exist_ok=True)

def _int(name: str, default: int = 0) -> int:
    try: return int(os.getenv(name, str(default)).strip())
    except ValueError: return default

@dataclass(frozen=True)
class Settings:
    api_id: int = _int('API_ID')
    api_hash: str = os.getenv('API_HASH','').strip()
    bot_token: str = os.getenv('BOT_TOKEN','').strip()
    owner_id: int = _int('OWNER_ID')
    gemini_api_key: str = os.getenv('GEMINI_API_KEY','').strip()
    gemini_model: str = os.getenv('GEMINI_MODEL','gemini-2.5-flash').strip()
    session_name: str = os.getenv('SESSION_NAME','special_user').strip()
    db_path: str = os.getenv('DB_PATH', str(STORAGE / 'special.db')).strip()
    log_level: str = os.getenv('LOG_LEVEL','INFO').strip().upper()

    def validate(self) -> list[str]:
        missing=[]
        if not self.api_id: missing.append('API_ID')
        if not self.api_hash: missing.append('API_HASH')
        if not self.bot_token: missing.append('BOT_TOKEN')
        if not self.owner_id: missing.append('OWNER_ID')
        return missing

settings = Settings()
