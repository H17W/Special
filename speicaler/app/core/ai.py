import asyncio
import os
import re
from typing import Optional, Tuple

from dotenv import load_dotenv
from google import genai

from app.core.database import get_setting

load_dotenv(".env", override=True)

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "gemini-3.8-flash").strip()
GEMINI_ENABLED = (
    (os.getenv("GEMINI_ENABLED") or "1").strip().lower()
    in {"1", "true", "yes", "on"}
)

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY غير موجود في ملف البيئة")
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _get_ai_trigger() -> str:
    try:
        value = get_setting("ai_trigger", "") or ""
        return str(value).strip().lstrip("@#")
    except Exception:
        return ""


def parse_request(text: str) -> Tuple[bool, str]:
    if not text:
        return False, ""
    text = str(text).strip()
    if not text:
        return False, ""
    triggers = ["سبيشل"]
    custom = _get_ai_trigger()
    if custom:
        triggers.append(custom)
    triggers = sorted({x.strip().lstrip("@#") for x in triggers if x.strip()}, key=len, reverse=True)
    lowered = text.casefold()
    for trigger in triggers:
        t = trigger.casefold()
        for prefix in (t, "@" + t):
            if lowered.startswith(prefix):
                remainder = text[len(prefix):].strip().lstrip(":،,-–—|+").strip()
                return (True, remainder) if remainder else (True, "")
    return False, ""


def _extract_output_text(interaction) -> str:
    text = getattr(interaction, "output_text", None)
    if text:
        return str(text).strip()
    output = getattr(interaction, "output", None)
    if output:
        parts = []
        for item in output:
            item_text = getattr(item, "text", None)
            if item_text:
                parts.append(str(item_text))
        if parts:
            return "\n".join(parts).strip()
    raise RuntimeError("Gemini لم يرجع نصًا في الاستجابة")


async def ask_gemini(prompt: str) -> str:
    if not GEMINI_ENABLED or get_setting("gemini_enabled", "1") == "0":
        raise RuntimeError("Gemini معطل في إعدادات البوت")
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("السؤال فارغ")
    client = _get_client()

    def _send():
        return client.interactions.create(model=GEMINI_MODEL, input=prompt)

    interaction = await asyncio.to_thread(_send)
    return _extract_output_text(interaction)


async def test_gemini() -> str:
    return await ask_gemini("قل مرحبا فقط")
