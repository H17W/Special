import asyncio
import json
import os
from typing import Any

from urllib import error, request

from dotenv import load_dotenv

load_dotenv(override=True)

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = (
    os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
).strip()
GEMINI_ENABLED = (
    os.getenv("GEMINI_ENABLED") or "1"
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/{model}:generateContent"
)


def _build_payload(prompt: str) -> dict[str, Any]:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt,
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
        },
    }


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []

    if not candidates:
        raise RuntimeError(
            "Gemini لم يرجع candidates في الاستجابة"
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    texts = []

    for part in parts:
        text = part.get("text")

        if text:
            texts.append(text)

    result = "\n".join(texts).strip()

    if not result:
        raise RuntimeError(
            "Gemini رجع استجابة بدون نص"
        )

    return result


def _request_gemini(prompt: str) -> str:
    if not GEMINI_ENABLED:
        raise RuntimeError(
            "Gemini معطل من GEMINI_ENABLED"
        )

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY غير موجود في ملف البيئة"
        )

    if not GEMINI_MODEL:
        raise RuntimeError(
            "GEMINI_MODEL غير محدد"
        )

    url = GEMINI_API_URL.format(
        model=GEMINI_MODEL
    )

    payload = _build_payload(prompt)

    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    req = request.Request(
        url=url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
    )

    try:
        with request.urlopen(
            req,
            timeout=60,
        ) as response:
            raw = response.read().decode(
                "utf-8",
                errors="replace",
            )

    except error.HTTPError as exc:
        response_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            details = json.loads(response_body)
            message = details.get(
                "error",
                {},
            ).get(
                "message",
                response_body,
            )
        except Exception:
            message = response_body

        raise RuntimeError(
            f"Gemini HTTP {exc.code}: {message}"
        ) from exc

    except error.URLError as exc:
        raise RuntimeError(
            f"تعذر الاتصال بـ Gemini: {exc.reason}"
        ) from exc

    except TimeoutError as exc:
        raise RuntimeError(
            "انتهت مهلة الاتصال بـ Gemini"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini رجع استجابة غير صالحة"
        ) from exc

    return _extract_text(data)


async def ask_gemini(
    prompt: str,
) -> str:
    """
    إرسال سؤال إلى Gemini بشكل غير متزامن.
    """

    if not isinstance(prompt, str):
        prompt = str(prompt)

    prompt = prompt.strip()

    if not prompt:
        raise ValueError(
            "السؤال فارغ"
        )

    return await asyncio.to_thread(
        _request_gemini,
        prompt,
    )


async def test_gemini() -> str:
    """
    اختبار بسيط للاتصال بـ Gemini.
    """

    return await ask_gemini(
        "قل مرحبا فقط"
    )
