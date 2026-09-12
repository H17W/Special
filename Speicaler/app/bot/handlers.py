import re

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters

from app.core.config import ADMIN_ID
from app.core.database import init_database, get_allowed_user, get_feature_permissions, add_ai_log, get_setting, set_setting, add_bot_access_log
from app.core.ai import ask_gemini, parse_request
from app.user.moderation import mute, unmute
from app.user.client import refresh_special, manager
from .keyboards import main_menu, automation_menu, broadcast_menu, access_menu, broadcast_confirm_menu, ai_menu

router = Router()
login_state = {}
waiting_for_mute = set()
waiting_for_unmute = set()
pending = {}
music_reply_targets = {}


def is_admin(message):
    return bool(ADMIN_ID and message.from_user and str(message.from_user.id) == str(ADMIN_ID))


def access_ok(user_id):
    if ADMIN_ID and str(user_id) == str(ADMIN_ID):
        return True
    row = get_allowed_user(user_id)
    return bool(row and row["status"] == "active")


def menu_for(uid):
    return main_menu(None, logged_in=manager.status(uid)) if is_admin_uid(uid) else main_menu(uid, get_feature_permissions(uid), logged_in=manager.status(uid))


def is_admin_uid(uid):
    return bool(ADMIN_ID and str(uid) == str(ADMIN_ID))


async def notify_bot_start(message: Message, allowed: bool):
    if not ADMIN_ID or not message.from_user or is_admin(message):
        return
    u = message.from_user
    name = u.full_name or "مستخدم"
    username = u.username
    url = f"https://t.me/{username}" if username else f"tg://user?id={u.id}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 فتح حساب الشخص", url=url)]])
    status = "✅ تم السماح" if allowed else "⛔ تم رفض الوصول"
    try:
        await message.bot.send_message(int(ADMIN_ID), f"👤 شخص دخل بوت Special\n\nالاسم: {name}\n🆔 ID: {u.id}\n🔗 Username: {('@' + username) if username else 'لا يوجد يوزر'}\n📌 النتيجة: {status}", reply_markup=markup)
    except Exception:
        pass


@router.message(F.text.regexp(r"^/start(?:@\w+)?$"))
async def start_handler(message: Message):
    init_database()
    uid = message.from_user.id if message.from_user else 0
    allowed = access_ok(uid)
    print(f"📩 /start وصل من {uid} | allowed={allowed}")
    u = message.from_user
    if u:
        add_bot_access_log(u.id, u.full_name or "مستخدم", u.username, "allowed" if allowed else "denied")
    await notify_bot_start(message, allowed)
    if get_setting("bot_paused", "0") == "1":
        return
    if not allowed:
        await message.answer("⛔ غير مصرح لك باستخدام Special.")
        return
    logged_in = bool(manager.status(uid))
    text = "🧠 أهلاً بك في Special\n\n" + ("حسابك متصل وجاهز للعمل 🚀" if logged_in else "قبل استخدام User Automation سجّل حساب Telegram الخاص بك 🔐")
    await message.answer(text, reply_markup=main_menu(None) if is_admin_uid(uid) else main_menu(uid, get_feature_permissions(uid), logged_in=logged_in))


@router.message(F.text.regexp(r"^/?تحديث$"))
async def refresh_handler(message: Message):
    uid = message.from_user.id if message.from_user else 0
    if not access_ok(uid):
        return
    try:
        result = await refresh_special()
        text = "✅ تم تحديث البوت بنجاح\n\n"
        text += "🖼️ تم تحديث بيانات وصورة التقليد الحالي." if result.get("mimic_refreshed") else "🟢 تم فحص الاتصال وقاعدة البيانات وقائمة الخاص."
        await message.answer(text)
    except Exception as exc:
        await message.answer(f"❌ تعذر تحديث البوت: {type(exc).__name__}")


@router.message()
async def text_handler(message: Message):
    uid = message.from_user.id if message.from_user else 0
    text_value = (message.text or "").strip()

    # هذه أوامر تشغيل/إيقاف البوت نفسه، ولا توقف User Automation أو مراقبة الخاص.
    if text_value in {"ايقاف البوت", "إيقاف البوت", "/ايقاف البوت", "/إيقاف البوت"}:
        if is_admin(message) and getattr(message.chat, "type", None) == "private":
            set_setting("bot_paused", "1")
            await message.answer("⏸️ تم إيقاف استجابة البوت للأوامر. مراقبة الخاص والوسائط والكتم مستمرة.")
        return

    if text_value in {"تفعيل", "/تفعيل"}:
        if is_admin(message) and getattr(message.chat, "type", None) == "private":
            set_setting("bot_paused", "0")
            await message.answer("▶️ تم تفعيل البوت واستعادة الاستجابة لجميع خصائصه.")
        return

    if get_setting("bot_paused", "0") == "1":
        return

    if not access_ok(uid):
        return

    state = login_state.get(uid)
    if state and getattr(message.chat, "type", None) != "private":
        await message.answer("🔐 تسجيل الدخول للحساب يتم داخل الخاص مع Special فقط حفاظًا على بياناتك.")
        return
    if state:
        action = state.get("action")
        if action == "phone":
            phone = (message.text or "").strip()
            if len(phone) < 7 or not phone.replace("+", "").replace(" ", "").isdigit():
                await message.answer("❌ أرسل رقم هاتف Telegram بصيغة دولية مثل +9665xxxxxxxx")
                return
            try:
                await manager.begin_login(uid, phone.replace(" ", ""))
                login_state[uid] = {"action": "code", "phone": phone.replace(" ", "")}
                await message.answer("📨 أرسل كود Telegram. تقدر تكتبه مثل 7 7 0 0 0 وسيتم جمع الأرقام تلقائيًا.")
            except Exception as exc:
                login_state.pop(uid, None)
                await message.answer(f"❌ تعذر إرسال كود Telegram: {type(exc).__name__}")
            return
        if action == "code":
            code = re.sub(r"\D", "", message.text or "")
            if not code:
                await message.answer("❌ أرسل الكود أرقامًا فقط")
                return
            try:
                result = await manager.finish_code(uid, code)
                if result == "2fa":
                    login_state[uid] = {"action": "password"}
                    await message.answer("🔐 حسابك عليه تحقق بخطوتين. أرسل كلمة مرور 2FA الآن. لن يتم حفظها في قاعدة البيانات.")
                else:
                    login_state.pop(uid, None)
                    await message.answer("✅ تم تسجيل حساب Telegram بنجاح وربطه بلوحتك الخاصة 🚀", reply_markup=main_menu(uid, get_feature_permissions(uid), logged_in=True))
            except Exception as exc:
                await message.answer(f"❌ كود Telegram غير صالح أو انتهت الجلسة: {type(exc).__name__}")
            return
        if action == "password":
            password = message.text or ""
            if not password:
                await message.answer("❌ أرسل كلمة مرور التحقق بخطوتين")
                return
            try:
                await manager.finish_password(uid, password)
                login_state.pop(uid, None)
                await message.answer("✅ تم تسجيل الدخول بنجاح. كلمة مرور 2FA لم يتم حفظها.", reply_markup=main_menu(uid, get_feature_permissions(uid), logged_in=True))
            except Exception as exc:
                await message.answer(f"❌ تعذر إكمال التحقق بخطوتين: {type(exc).__name__}")
            return

    if message.text:
        ai_ok, ai_prompt = parse_request(message.text)
        if ai_ok and ai_prompt:
            try:
                answer = await ask_gemini(ai_prompt)
                if answer:
                    await message.answer(answer[:4000])
                    add_ai_log("bot", uid, message.from_user.full_name if message.from_user else "", message.from_user.username if message.from_user else None, message.chat.id, getattr(message.chat, "type", "unknown"), ai_prompt, answer)
                else:
                    await message.answer("⚠️ الذكاء الاصطناعي مغلق أو مفتاح Gemini غير مضبوط.")
            except Exception as exc:
                await message.answer(f"❌ تعذر تشغيل Gemini: {type(exc).__name__}")
            return

    if uid in waiting_for_mute:
        waiting_for_mute.discard(uid)
        try:
            target = int((message.text or "").strip())
        except ValueError:
            await message.answer("❌ أرسل Telegram ID رقمي فقط.")
            return
        mute(target)
        await message.answer(f"🔇 تم كتم المستخدم بنجاح\n\nID: {target}", reply_markup=automation_menu(is_admin_uid(uid)))
        return

    if uid in waiting_for_unmute:
        waiting_for_unmute.discard(uid)
        try:
            target = int((message.text or "").strip())
        except ValueError:
            await message.answer("❌ أرسل Telegram ID رقمي فقط.")
            return
        ok = unmute(target)
        await message.answer(("🔊 تم إلغاء كتم المستخدم بنجاح." if ok else "ℹ️ المستخدم غير موجود في قائمة المكتومين.") + f"\n\nID: {target}", reply_markup=automation_menu(is_admin_uid(uid)))
        return

    state = pending.get(uid)
    if not state:
        return

    action = state.get("action")
    if action == "dev_permission_search":
        if not is_admin_uid(uid):
            pending.pop(uid, None)
            return
        raw = (message.text or "").strip()
        try:
            target = int(raw)
        except ValueError:
            await message.answer("❌ أرسل Telegram ID رقمي فقط.")
            return
        pending.pop(uid, None)
        row = get_allowed_user(target)
        if not row:
            await message.answer(f"❌ المستخدم {target} غير موجود في قائمة المسموح لهم.", reply_markup=main_menu(None))
            return
        from app.core.permissions import FEATURES
        perms = get_feature_permissions(target)
        enabled = sum(1 for key, _ in FEATURES if perms.get(key, False))
        disabled = len(FEATURES) - enabled
        from .keyboards import back
        text = (f"🔍 فحص صلاحيات المستخدم\n\n👤 {row['display_name'] or 'مستخدم'}\n🆔 {target}\n"
                f"📌 الحالة: {row['status']}\n\n🟢 الصلاحيات المفعلة: {enabled}\n🔴 الصلاحيات المقفلة: {disabled}")
        await message.answer(text, reply_markup=back('access_user:'+str(target)))
        return

    if action == "music_search":
        query = (message.text or "").strip()
        pending.pop(uid, None)
        if not query:
            await message.answer("❌ اكتب اسم الأغنية أو الفنان أو كلمات البحث.")
            return
        progress = await message.answer("🔎 جارٍ البحث عن الصوت... ⏳")
        try:
            from app.core.music import search_music
            results = await search_music(query)
            try:
                await progress.delete()
            except Exception:
                pass
            from .keyboards import music_results_menu, back
            if not results:
                await message.answer("🎵 ما لقيت نتيجة صوتية قابلة للتنزيل من المصدر المتاح.", reply_markup=back("music"), reply_parameters=ReplyParameters(message_id=message.message_id))
                return
            music_reply_targets[uid] = {str(r.get('identifier')): message.message_id for r in results if r.get('identifier')}
            await message.answer("🎧 اختر النتيجة التي تريد جلبها", reply_markup=music_results_menu(results), reply_parameters=ReplyParameters(message_id=message.message_id))
        except Exception as exc:
            try:
                await progress.delete()
            except Exception:
                pass
            await message.answer(f"❌ تعذر البحث عن الصوت: {type(exc).__name__}", reply_markup=back("music"), reply_parameters=ReplyParameters(message_id=message.message_id))
        return

    if action == "ai_trigger_set":
        trigger = (message.text or "").strip().lstrip("@#")
        if not trigger:
            await message.answer("❌ اكتب الاسم الذي تريد استخدامه.")
            return
        if len(trigger) > 32:
            await message.answer("❌ الاسم طويل جدًا.")
            return
        set_setting("ai_trigger", trigger)
        pending.pop(uid, None)
        await message.answer(f"✅ تم تعيين اسم الذكاء الإضافي: {trigger}", reply_markup=ai_menu(get_setting("gemini_enabled", "1") != "0", trigger))
        return

    if action == "broadcast_text":
        pending[uid] = {"action": "broadcast_confirm", "text": message.text or ""}
        await message.answer(f"📢 معاينة الإذاعة\n\n{message.text or '[رسالة بدون نص]'}\n\nهل تريد إرسالها الآن؟", reply_markup=broadcast_confirm_menu())
        return

    if action == "broadcast_exclude":
        pending.pop(uid, None)
        raw = (message.text or "").strip()
        target = None
        try:
            target = int(raw)
        except ValueError:
            try:
                from app.user.client import resolve_username
                target = await resolve_username(raw)
            except Exception:
                target = None
        if not target:
            await message.answer("❌ أرسل ID رقمي أو @username لشخص حقيقي في الخاص.", reply_markup=broadcast_menu())
            return
        from app.core.database import set_broadcast_exclusion
        set_broadcast_exclusion(int(target))
        await message.answer("🚫 تم استثناءه من الإذاعة", reply_markup=broadcast_menu())
        return

    if action == "private_search":
        from app.core.database import search_private_chats
        query = (message.text or "").strip()
        pending.pop(uid, None)
        rows = search_private_chats(query, 25)
        from .keyboards import kb, btn
        if not rows:
            await message.answer("🔎 ما لقيت شخص بهذا الاسم أو اليوزر أو الـID.", reply_markup=kb([[btn("🔙 إدارة الخاص", "private")]]))
            return
        buttons = [[btn(f"👤 {r['display_name'] or r['user_id']}", f"chat:{r['user_id']}")] for r in rows]
        buttons.append([btn("🔙 إدارة الخاص", "private")])
        await message.answer(f"🔎 نتائج البحث عن: {query}", reply_markup=kb(buttons))
        return

    if action == "access_add":
        pending.pop(uid, None)
        try:
            target = int((message.text or "").strip())
        except ValueError:
            await message.answer("❌ أرسل Telegram ID رقمي فقط.", reply_markup=access_menu())
            return
        if str(target) == str(ADMIN_ID):
            await message.answer("ℹ️ هذا هو المالك أصلًا.", reply_markup=access_menu())
            return
        from app.core.database import add_allowed_user, ensure_feature_permissions
        add_allowed_user(target, None, str(target), None)
        ensure_feature_permissions(target)
        await message.answer("✅ تم السماح للمستخدم باستخدام Special", reply_markup=access_menu())
        return

    if action == "access_remove":
        pending.pop(uid, None)
        try:
            target = int((message.text or "").strip())
        except ValueError:
            await message.answer("❌ أرسل Telegram ID رقمي فقط.", reply_markup=access_menu())
            return
        from app.core.database import remove_allowed_user
        remove_allowed_user(target)
        await message.answer("🗑️ تمت إزالة صلاحية المستخدم.", reply_markup=access_menu())
