import asyncio
import os
from typing import Optional

from dotenv import load_dotenv
from google import genai

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
        raise RuntimeError(
            "GEMINI_API_KEY غير موجود في ملف البيئة"
        )

    if _client is None:
        _client = genai.Client(
            api_key=GEMINI_API_KEY
        )

    return _client


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

    raise RuntimeError(
        "Gemini لم يرجع نصًا في الاستجابة"
    )


async def ask_gemini(prompt: str) -> str:
    if not GEMINI_ENABLED:
        raise RuntimeError(
            "Gemini معطل في إعدادات البوت"
        )

    prompt = str(prompt or "").strip()

    if not prompt:
        raise ValueError(
            "السؤال فارغ"
        )

    client = _get_client()

    def _send():
        return client.interactions.create(
            model=GEMINI_MODEL,
            input=prompt,
        )

    interaction = await asyncio.to_thread(_send)

    return _extract_output_text(interaction)


async def test_gemini() -> str:
    return await ask_gemini(
        "قل مرحبا فقط"
    )
