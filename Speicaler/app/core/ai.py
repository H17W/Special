from .config import settings
class AIError(Exception): pass
async def ask(prompt):
    try:
        from google import genai
        client=genai.Client(api_key=settings.gemini_api_key)
        r=client.models.generate_content(model=settings.gemini_model,contents=prompt)
        return getattr(r,'text',None) or 'لم يرجع الذكاء الاصطناعي نصاً'
    except Exception as e: raise AIError(str(e))
