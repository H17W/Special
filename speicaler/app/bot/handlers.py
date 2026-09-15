from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from app.core.config import ADMIN_ID
from app.core.database import init_database, get_allowed_user, get_feature_permissions, add_ai_log, get_setting, set_setting, add_bot_access_log, register_denied_access, mark_denied_access_notified, reset_access_attempts, add_allowed_user, ensure_feature_permissions, remove_allowed_user
from app.core.ai import ask_gemini, parse_request
from app.user.moderation import mute, unmute, mute_in_chat, unmute_in_chat
from app.user.client import refresh_special, start_authorized_user_client, is_user_logged_in, set_active_client, get_or_create_user_client, client as user_client
from .keyboards import main_menu, automation_menu, broadcast_menu, access_menu, broadcast_confirm_menu, ai_menu
from .login import active_login, login_prompt

router = Router()
waiting_for_mute = set()
waiting_for_unmute = set()
waiting_for_chat_mute = {}
waiting_for_chat_unmute = {}
pending = {}


def is_admin(message):
    return bool(ADMIN_ID and message.from_user and str(message.from_user.id) == str(ADMIN_ID))


def access_ok(user_id):
    if ADMIN_ID and str(user_id) == str(ADMIN_ID):
        return True
    row = get_allowed_user(user_id)
    return bool(row and row["status"] == "active")


def menu_for(uid):
    return main_menu(None) if is_admin_uid(uid) else main_menu(uid, get_feature_permissions(uid))


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
    # Fully ignore users who were already restricted, including /start spam.
    existing = get_allowed_user(uid) if uid else None
    if existing and existing["status"] == "suspended":
        return
    allowed = access_ok(uid)
    print(f"📩 /start وصل من {uid} | allowed={allowed}")
    u = message.from_user
    if u:
        add_bot_access_log(u.id, u.full_name or "مستخدم", u.username, "allowed" if allowed else "denied")
    if get_setting("bot_paused", "0") == "1":
        return
    if not allowed:
        # Every unauthorized /start gets the agreed denial message and one owner notification.
        await notify_bot_start(message, False)
        # Once restricted, ignore the user completely to avoid processing spam.
        existing = get_allowed_user(uid)
        if existing and existing["status"] == "suspended":
            return

        result = register_denied_access(uid)
        if result["restricted"]:
            add_allowed_user(uid, u.username if u else None, u.full_name if u else "مستخدم", None)
            from app.core.database import update_allowed_status
            update_allowed_status(uid, "suspended", None)
            await message.answer("⛔ تم تقييدك من استخدام Special بسبب تكرار محاولات الدخول بسرعة. إذا كنت بحاجة إلى الوصول يرجى التواصل مع المطور.")

            if result["notify_owner"]:
                try:
                    await message.bot.send_message(
                        int(ADMIN_ID),
                        f"⚠️ تنبيه: المستخدم {u.full_name if u else 'مستخدم'} (ID: {uid}) كرر طلب /start بشكل مزعج خلال فترة قصيرة وتم تقييده تلقائيًا.\n\nهل ترغب في حظره؟"
                    )
                except Exception:
                    pass
                mark_denied_access_notified(uid)
            return

        if result["attempts"] == 2:
            await message.answer("⚠️ تم تسجيل إنذار لك بسبب تكرار محاولة الدخول. إذا كررت المحاولة مرة أخرى خلال فترة قصيرة فسيتم تقييدك من استخدام Special.")
        else:
            await message.answer("⛔ غير مصرح لك باستخدام Special. يرجى التواصل مع المطور.")
        return
    reset_access_attempts(uid)
    try:
        # The developer account is already authenticated by the terminal-launched
        # Special User Automation session. Never ask the developer to log in again.
        if is_admin_uid(uid):
            set_active_client(await get_or_create_user_client(uid), uid)
            await message.answer("🧠 أهلاً بك في Special\n\nلوحة التحكم الرئيسية:", reply_markup=menu_for(uid))
            return

        if not await is_user_logged_in(uid):
            if not active_login(uid):
                await login_prompt(message)
            return
        await start_authorized_user_client(uid)
    except Exception as exc:
        await message.answer(f"❌ تعذر تشغيل جلسة حسابك: {type(exc).__name__}")
        return
    set_active_client(await get_or_create_user_client(uid), uid)
    await message.answer("🧠 أهلاً بك في Special\n\nلوحة التحكم الرئيسية:", reply_markup=menu_for(uid))


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


async def _resolve_bot_user_target(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        if value.lstrip("-").isdigit():
            return await user_client.get_entity(int(value))
        return await user_client.get_entity(value.lstrip("@"))
    except Exception:
        return None


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

    try:
        set_active_client(await get_or_create_user_client(uid), uid)
    except Exception:
        pass

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
        target = await _resolve_bot_user_target(message.text)
        if not target:
            await message.answer("❌ أرسل Telegram ID أو @username صحيح.")
            return
        mute(target.id, getattr(target, "username", None), getattr(target, "first_name", None) or getattr(target, "last_name", None))
        await message.answer(f"🔇 تم كتم المستخدم في الخاص بنجاح\n\n👤 {getattr(target, 'first_name', None) or 'مستخدم'}\n🆔 ID: {target.id}\n🔗 Username: {('@' + target.username) if getattr(target, 'username', None) else 'لا يوجد يوزر'}", reply_markup=automation_menu())
        return

    if uid in waiting_for_unmute:
        waiting_for_unmute.discard(uid)
        target = await _resolve_bot_user_target(message.text)
        if not target:
            await message.answer("❌ أرسل Telegram ID أو @username صحيح.")
            return
        ok = unmute(target.id)
        await message.answer(("🔊 تم إلغاء الكتم عن المستخدم في الخاص." if ok else "ℹ️ المستخدم غير موجود في قائمة مكتومي الخاص.") + f"\n\n🆔 ID: {target.id}", reply_markup=automation_menu())
        return

    if uid in waiting_for_chat_mute:
        chat_id = waiting_for_chat_mute[uid]
        if chat_id is None:
            try:
                chat_id = int((message.text or "").strip())
            except ValueError:
                await message.answer("❌ أرسل Chat ID رقمي للقروب أو القناة.")
                return
            waiting_for_chat_mute[uid] = chat_id
            await message.answer("الخطوة 2 من 2\nأرسل Telegram ID أو @username للمستخدم الذي تريد كتمه.")
            return
        target = await _resolve_bot_user_target(message.text)
        if not target:
            await message.answer("❌ أرسل Telegram ID أو @username صحيح للمستخدم.")
            return
        waiting_for_chat_mute.pop(uid, None)
        try:
            mute_in_chat(chat_id, target.id, getattr(target, "username", None), getattr(target, "first_name", None) or getattr(target, "last_name", None))
            await message.answer(f"🔇 تم كتم المستخدم في القروب/القناة بنجاح\n\n💬 Chat ID: {chat_id}\n👤 {getattr(target, 'first_name', None) or 'مستخدم'}\n🆔 ID: {target.id}\n🔗 Username: {('@' + target.username) if getattr(target, 'username', None) else 'لا يوجد يوزر'}", reply_markup=automation_menu())
        except Exception as exc:
            await message.answer(f"❌ تعذر كتم المستخدم في هذا القروب/القناة: {type(exc).__name__}", reply_markup=automation_menu())
        return

    if uid in waiting_for_chat_unmute:
        chat_id = waiting_for_chat_unmute[uid]
        if chat_id is None:
            try:
                chat_id = int((message.text or "").strip())
            except ValueError:
                await message.answer("❌ أرسل Chat ID رقمي للقروب أو القناة.")
                return
            waiting_for_chat_unmute[uid] = chat_id
            await message.answer("الخطوة 2 من 2\nأرسل Telegram ID أو @username للمستخدم الذي تريد فك كتمه.")
            return
        target = await _resolve_bot_user_target(message.text)
        if not target:
            await message.answer("❌ أرسل Telegram ID أو @username صحيح للمستخدم.")
            return
        waiting_for_chat_unmute.pop(uid, None)
        ok = unmute_in_chat(chat_id, target.id)
        await message.answer(("🔊 تم إلغاء كتم المستخدم في القروب/القناة." if ok else "ℹ️ المستخدم غير مكتوم في هذا القروب/القناة.") + f"\n\n💬 Chat ID: {chat_id}\n🆔 ID: {target.id}", reply_markup=automation_menu())
        return

    state = pending.get(uid)
    if not state:
        return

    action = state.get("action")
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


    if action == "access_unban":
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
            await message.answer("❌ أرسل ID رقمي أو @username صحيح.", reply_markup=access_menu())
            return
        remove_allowed_user(int(target))
        reset_access_attempts(int(target))
        await message.answer("✅ تم إلغاء حظر المستخدم. سيحتاج المطور إلى منحه الصلاحية مجددًا قبل استخدام البوت.", reply_markup=access_menu())
        return
