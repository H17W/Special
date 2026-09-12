import asyncio
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv(override=True)

try:
    from google import genai
except Exception:
    genai = None


@lru_cache(maxsize=1)
def _client():
    if genai is None:
        return None
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    return genai.Client(api_key=key)


def is_enabled():
    return bool(_client()) and os.getenv("GEMINI_ENABLED", "1") != "0"


def _sync_generate(prompt: str):
    c = _client()
    if c is None:
        raise RuntimeError("GEMINI_API_KEY غير مضبوط أو مكتبة google-genai غير مثبتة")
    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    response = c.models.generate_content(model=model, contents=prompt)
    return getattr(response, "text", None) or ""


async def ask_gemini(prompt: str):
    if not is_enabled():
        return None
    return await asyncio.to_thread(_sync_generate, prompt)
