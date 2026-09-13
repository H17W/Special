from __future__ import annotations
import asyncio
from .config import settings

class AIError(RuntimeError): pass

async def ask(prompt:str)->str:
    if not settings.gemini_api_key: raise AIError('GEMINI_API_KEY غير مضبوط في .env')
    try:
        from google import genai
        client=genai.Client(api_key=settings.gemini_api_key)
        def call(): return client.models.generate_content(model=settings.gemini_model, contents=prompt)
        response=await asyncio.to_thread(call)
        text=getattr(response,'text',None)
        if not text: raise AIError('Gemini returned an empty response')
        return text.strip()
    except AIError: raise
    except Exception as e: raise AIError(str(e)) from e
