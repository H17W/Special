import asyncio
import os
from typing import Optional, Tuple

from dotenv import load_dotenv
from google import genai

from app.core.database import get_setting

load_dotenv(".env", override=True)

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = (
    os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
).strip()

GEMINI_ENABLED = (
    (os.getenv("GEMINI_ENABLED") or "1")
    .strip()
    .lower()
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


def _get_ai_trigger() -> str:
    """
    الاسم الإضافي الذي يحدده المالك من لوحة الذكاء الاصطناعي.
    الافتراضي: لا يوجد اسم إضافي.
    """
    try:
        value = get_setting("ai_trigger", "") or ""
        return str(value).strip().lstrip("@#")
    except Exception:
        return ""


def parse_request(text: str) -> Tuple[bool, str]:
    """
    يحدد هل الرسالة موجهة إلى الذكاء الاصطناعي أم لا.

    الصيغ المقبولة:
        سبيشل كيف حالك
        @سبيشل كيف حالك
        حاتم كيف حالك
        @حاتم كيف حالك

    الاسم الإضافي مأخوذ من إعداد ai_trigger.
    """

    if not text:
        return False, ""

    text = str(text).strip()

    if not text:
        return False, ""

    # الاسم الأساسي
    triggers = ["سبيشل"]

    # الاسم الإضافي من لوحة التحكم
    custom_trigger = _get_ai_trigger()

    if custom_trigger:
        triggers.append(custom_trigger)

    # ترتيب الأطول أولًا حتى لا يحدث تعارض
    triggers = sorted(
        {
            trigger.strip().lstrip("@#")
            for trigger in triggers
            if trigger and trigger.strip()
        },
        key=len,
        reverse=True,
    )

    lowered = text.casefold()

    for trigger in triggers:
        trigger_lower = trigger.casefold()

        # "سبيشل السؤال"
        if lowered.startswith(trigger_lower):
            remainder = text[len(trigger):].strip()

            # يدعم:
            # سبيشل: السؤال
            # سبيشل، السؤال
            # سبيشل - السؤال
            # سبيشل السؤال
            remainder = remainder.lstrip(
                ":،,-–—|"
            ).strip()

            if remainder:
                return True, remainder

            return True, ""

        # "@سبيشل السؤال"
        mentioned = "@" + trigger_lower

        if lowered.startswith(mentioned):
            remainder = text[len(trigger) + 1:].strip()

            remainder = remainder.lstrip(
                ":،,-–—|"
            ).strip()

            if remainder:
                return True, remainder

            return True, ""

    return False, ""


def _extract_output_text(interaction) -> str:
    text = getattr(
        interaction,
        "output_text",
        None,
    )

    if text:
        return str(text).strip()

    output = getattr(
        interaction,
        "output",
        None,
    )

    if output:
        parts = []

        for item in output:
            item_text = getattr(
                item,
                "text",
                None,
            )

            if item_text:
                parts.append(
                    str(item_text)
                )

        if parts:
            return "\n".join(
                parts
            ).strip()

    raise RuntimeError(
        "Gemini لم يرجع نصًا في الاستجابة"
    )


async def ask_gemini(prompt: str) -> str:
    if not GEMINI_ENABLED:
        raise RuntimeError(
            "Gemini معطل في إعدادات البوت"
        )

    prompt = str(
        prompt or ""
    ).strip()

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

    interaction = await asyncio.to_thread(
        _send
    )

    return _extract_output_text(
        interaction
    )


async def test_gemini() -> str:
    return await ask_gemini(
        "قل مرحبا فقط"
    )
