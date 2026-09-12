import asyncio
import os
import re

from google import genai

from app.core.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_ENABLED
from app.core.database import get_setting


def _enabled_flag() -> bool:
    setting = get_setting("gemini_enabled", GEMINI_ENABLED)
    return str(setting or "1") != "0"


def is_enabled() -> bool:
    return bool(GEMINI_API_KEY) and _enabled_flag()


def get_trigger() -> str:
    return (get_setting("ai_trigger", "") or "").strip()


def parse_request(text: str):
    if not text:
        return False, ""
    triggers = ["سبيشل"]
    custom = get_trigger()
    if custom and custom not in triggers:
        triggers.append(custom)
    for trigger in sorted(triggers, key=len, reverse=True):
        # Accept: سبيشل السؤال | سبيشل: السؤال | سبيشل + السؤال
        pattern = rf"^\s*{re.escape(trigger)}(?:\s*\+\s*|\s*[:،,-]\s*|\s+)(.+)$"
        match = re.match(pattern, text, re.IGNORECASE | re.DOTALL)
        if match and match.group(1).strip():
            return True, match.group(1).strip()
    return False, ""


def _sync_generate(prompt: str) -> str:
    if not is_enabled():
        return ""
    client = genai.Client(api_key=GEMINI_API_KEY)
    model = get_setting("gemini_model", GEMINI_MODEL) or GEMINI_MODEL
    response = client.models.generate_content(model=model, contents=prompt)
    return (getattr(response, "text", None) or "").strip()


async def ask_gemini(prompt: str) -> str | None:
    if not is_enabled():
        return None
    return await asyncio.to_thread(_sync_generate, prompt)
