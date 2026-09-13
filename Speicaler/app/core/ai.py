import asyncio
import os
from typing import Optional, Tuple
from dotenv import load_dotenv
from google import genai
from app.core.database import get_setting
ROOT_ENV=os.path.abspath(os.path.join(os.path.dirname(__file__),"../..",".env")); load_dotenv(ROOT_ENV,override=False); load_dotenv(override=True)
GEMINI_API_KEY=(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip(); GEMINI_MODEL=(os.getenv("GEMINI_MODEL") or "gemini-3.8-flash").strip(); GEMINI_ENABLED=(os.getenv("GEMINI_ENABLED") or "1").strip().lower() in {"1","true","yes","on"}
_client:Optional[genai.Client]=None
def _get_client():
 global _client
 if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY غير موجود في ملف البيئة")
 if _client is None: _client=genai.Client(api_key=GEMINI_API_KEY)
 return _client
def _get_ai_trigger():
 try:return str(get_setting("ai_trigger","") or "").strip().lstrip("@#")
 except Exception:return ""
def parse_request(text:str)->Tuple[bool,str]:
 if not text:return False,""
 text=str(text).strip(); triggers=["سبيشل"]; custom=_get_ai_trigger()
 if custom:triggers.append(custom)
 for trigger in sorted({x.strip().lstrip("@#") for x in triggers if x.strip()},key=len,reverse=True):
  for prefix in (trigger,"@"+trigger):
   if text.casefold().startswith(prefix.casefold()):return True,text[len(prefix):].strip().lstrip(":،,-–—|+").strip()
 return False,""
def _text(response):
 value=getattr(response,"text",None) or getattr(response,"output_text",None)
 if value:return str(value).strip()
 output=getattr(response,"output",None)
 if output:
  parts=[str(getattr(x,"text")) for x in output if getattr(x,"text",None)]
  if parts:return "\n".join(parts).strip()
 raise RuntimeError("Gemini لم يرجع نصًا في الاستجابة")
async def ask_gemini(prompt:str)->str:
 if not GEMINI_ENABLED or get_setting("gemini_enabled","1")=="0":raise RuntimeError("Gemini معطل في إعدادات البوت")
 prompt=str(prompt or "").strip()
 if not prompt:raise ValueError("السؤال فارغ")
 client=_get_client()
 def call():
  try:return client.models.generate_content(model=GEMINI_MODEL,contents=prompt)
  except Exception as first:
   try:return client.interactions.create(model=GEMINI_MODEL,input=prompt)
   except Exception:raise first
 return _text(await asyncio.to_thread(call))
async def test_gemini()->str:return await ask_gemini("قل مرحبا فقط")
