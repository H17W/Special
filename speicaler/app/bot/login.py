import re
from aiogram import Router, F
from aiogram.filters import BaseFilter
from aiogram.types import Message
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError

from app.core.config import API_ID, API_HASH, ADMIN_ID
from app.core.database import get_allowed_user, get_user_session, save_user_session, add_log
from app.user.client import get_or_create_user_client, start_authorized_user_client, session_path_for_bot_user
from app.bot.keyboards import main_menu

router = Router()
LOGIN = {}


def is_admin_uid(uid):
    return bool(ADMIN_ID and str(uid) == str(ADMIN_ID))

def access_ok(uid):
    if is_admin_uid(uid):
        return True
    row = get_allowed_user(uid)
    return bool(row and row["status"] == "active")


def normalize_phone(value):
    raw = (value or "").strip()
    # Accept normal spaces, non-breaking spaces and common separators.
    raw = raw.replace("\u00a0", " ")
    raw = re.sub(r"[\s\-()]+", "", raw)
    # Accept Arabic-Indic digits too.
    raw = raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    if not re.fullmatch(r"\+?[0-9]{8,16}", raw):
        return None
    return raw if raw.startswith("+") else "+" + raw


def code_digits(value):
    return "".join(re.findall(r"[0-9]", value or ""))


def begin_login(uid):
    LOGIN[int(uid)] = {"step": "phone", "digits": ""}


def active_login(uid):
    return int(uid) in LOGIN


def cancel_login(uid):
    LOGIN.pop(int(uid), None)


class LoginActiveFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and active_login(message.from_user.id))


async def login_prompt(message: Message):
    uid = int(message.from_user.id)
    begin_login(uid)
    await message.answer(
        "🔐 تسجيل دخول حساب Telegram\n\n"
        "أرسل رقم جوالك بصيغة دولية\n"
        "مثال: +9665XXXXXXXX\n\n"
        "بعدها سأطلب منك كود Telegram ثم التحقق بخطوتين إذا كان مفعّلًا.")


@router.message(F.text.regexp(r"^/login(?:@\w+)?$"))
async def login_command(message: Message):
    uid = int(message.from_user.id)
    if not access_ok(uid):
        return
    if is_admin_uid(uid):
        await message.answer("✅ حساب المطور مسجل دخول أصلًا عبر جلسة Special User Automation ولا يحتاج تسجيل دخول من البوت.")
        return
    row = get_user_session(uid)
    if row and row["status"] == "active":
        try:
            if await start_authorized_user_client(uid):
                await message.answer("✅ حسابك مسجل دخول بالفعل ويعمل الآن.")
                return
        except Exception:
            pass
    await login_prompt(message)


@router.message(LoginActiveFilter())
async def login_flow(message: Message):
    uid = int(message.from_user.id)
    # The developer is already authenticated by the terminal-launched owner session.
    if is_admin_uid(uid):
        cancel_login(uid)
        return
    state = LOGIN.get(uid)
    if not state or not access_ok(uid):
        return

    text = (message.text or "").strip()
    step = state.get("step")
    uc = await get_or_create_user_client(uid)

    if step == "phone":
        phone = normalize_phone(text)
        if not phone:
            await message.answer("❌ رقم غير صحيح\nأرسله بصيغة دولية مثل +9665XXXXXXXX")
            return
        try:
            if not uc.is_connected():
                await uc.connect()
            sent = await uc.send_code_request(phone)
            LOGIN[uid] = {
                "step": "code",
                "phone": phone,
                "phone_code_hash": sent.phone_code_hash,
                "digits": "",
            }
            await message.answer(
                "📩 تم إرسال رمز التحقق إليك عبر Telegram\n\n"
                "يرجى إدخال رمز التحقق مع وضع مسافة بين كل رقم\n"
                "مثال: 1 1 1 7 7")
        except Exception as exc:
            cancel_login(uid)
            await message.answer(f"❌ تعذر إرسال كود الدخول: {type(exc).__name__}")
        return

    if step == "code":
        digits = code_digits(text)
        if not digits:
            await message.answer("❌ أرسل أرقام الكود فقط.")
            return
        state["digits"] = (state.get("digits", "") + digits)[:8]
        # Telegram login codes are normally 5 digits. If a 6-digit code is supplied,
        # allow that too; a single invalid attempt does not discard the login state.
        if len(state["digits"]) < 5:
            await message.answer(f"🔢 تم استلام {len(state['digits'])} أرقام — أكمل باقي الكود.")
            return
        code = state["digits"]
        try:
            await uc.sign_in(phone=state["phone"], code=code, phone_code_hash=state["phone_code_hash"])
        except SessionPasswordNeededError:
            state["step"] = "password"
            state["digits"] = ""
            await message.answer("🔒 حسابك عليه تحقق بخطوتين\nأرسل كلمة مرور التحقق بخطوتين.")
            return
        except PhoneCodeInvalidError:
            if len(code) == 5:
                state["digits"] = ""
                await message.answer("❌ الكود غير صحيح\nأرسل الكود من جديد.")
            else:
                state["digits"] = ""
                await message.answer("❌ كود Telegram غير صحيح أو منتهي\nأعد إرسال الكود.")
            return
        except PhoneCodeExpiredError:
            state["step"] = "phone"
            state.pop("phone_code_hash", None)
            state["digits"] = ""
            await message.answer("⌛ انتهت صلاحية الكود\nأرسل رقم الجوال من جديد.")
            return
        except Exception as exc:
            await message.answer(f"❌ تعذر تسجيل الدخول: {type(exc).__name__}")
            return

        await finish_login(message, uid, uc)
        return

    if step == "password":
        password = text
        if not password:
            await message.answer("❌ أرسل كلمة مرور التحقق بخطوتين.")
            return
        try:
            await uc.sign_in(password=password)
        except Exception as exc:
            await message.answer(f"❌ كلمة مرور التحقق بخطوتين غير صحيحة: {type(exc).__name__}")
            return
        await finish_login(message, uid, uc)


async def finish_login(message: Message, uid: int, uc):
    try:
        me = await uc.get_me()
        path = session_path_for_bot_user(uid)
        save_user_session(uid, path, int(me.id), None, "active")
        ok = await start_authorized_user_client(uid)
        if not ok:
            raise RuntimeError("session_not_authorized")
        cancel_login(uid)
        await message.answer(
            "✅ تم تسجيل حسابك بنجاح\n\n"
            "حسابك الآن مستقل عن حساب المطور وتعمل عليه خصائص الخاص والأتمتة.",
            reply_markup=main_menu(uid),
        )
    except Exception as exc:
        add_log("operation_log", "user_login_finish_failed", f"bot_user={uid}:{type(exc).__name__}")
        await message.answer(f"❌ تم تسجيل الدخول لكن تعذر تشغيل الأتمتة: {type(exc).__name__}")
