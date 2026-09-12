import os
from dotenv import load_dotenv

load_dotenv(override=True)

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
API_ID = (os.getenv("API_ID") or "").strip()
API_HASH = (os.getenv("API_HASH") or "").strip()

ADMIN_ID = (
    os.getenv("ADMIN_ID")
    or os.getenv("OWNER_ID")
    or ""
).strip()

GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or ""
).strip()

GEMINI_MODEL = (
    os.getenv("GEMINI_MODEL")
    or "gemini-3.6-flash"
).strip()

GEMINI_ENABLED = (
    os.getenv("GEMINI_ENABLED")
    or "1"
).strip()
