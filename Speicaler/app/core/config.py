import os
from dotenv import load_dotenv

load_dotenv(override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
ADMIN_ID = os.getenv("ADMIN_ID") or os.getenv("OWNER_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_ENABLED = os.getenv("GEMINI_ENABLED", "1")
