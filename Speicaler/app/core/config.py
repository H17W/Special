from __future__ import annotations
import os
from pathlib import Path
class Settings:
    api_id=int(os.getenv('API_ID','0') or 0); api_hash=os.getenv('API_HASH',''); bot_token=os.getenv('BOT_TOKEN',''); owner_id=int(os.getenv('OWNER_ID','0') or 0)
    gemini_api_key=os.getenv('GEMINI_API_KEY',''); gemini_model=os.getenv('GEMINI_MODEL','gemini-2.5-flash')
    session_name=os.getenv('SESSION_NAME','special'); db_path=os.getenv('DB_PATH','special.db')
    def validate(self):
        return [k for k,v in {'API_ID':self.api_id,'API_HASH':self.api_hash,'BOT_TOKEN':self.bot_token,'OWNER_ID':self.owner_id}.items() if not v]
settings=Settings(); ROOT=Path(__file__).resolve().parents[2]; STORAGE=ROOT/'storage'; STORAGE.mkdir(exist_ok=True)
