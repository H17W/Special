from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.core.permissions import FEATURES


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def btn(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu(user_id=None, allowed=None):
    if allowed is None:
        allowed = {k: True for k, _ in FEATURES}
    def any_cat(cat):
        return any(allowed.get(k, False) for k, _ in FEATURES if k.startswith(cat + "."))
    rows = []
    for cat, label, icon in [
        ("automation", "User Automation", "🧠"),
        ("private", "إدارة الخاص", "📥"),
        ("storage", "التخزين والنسخ الاحتياطي", "🗃"),
        ("important", "الرسائل المهمة", "⭐"),
        ("broadcast", "الإذاعة", "📢"),
        ("protection", "الحماية", "🛡"),
        ("stats", "الإحصائيات", "📊"),
        ("settings", "الإعدادات", "⚙️"),
    ]:
        if any_cat(cat):
            rows.append([btn(f"{icon} {label}", cat)])
    if user_id is None:
        rows.append([btn("🤖 الذكاء الاصطناعي", "ai_settings")])
        rows.append([btn("👑 إدارة المستخدمين", "access")])
    return kb(rows)


def automation_menu():
    return kb([
        [btn("📖 أوامر المسح والكتم", "private_commands"), btn("🔄 تحديث", "runtime_refresh")],
        [btn("🔇 كتم الخاص", "mute_private_user"), btn("🔊 فك كتم الخاص", "unmute_private_user")],
        [btn("🔇 كتم قروب/قناة", "mute_chat_user"), btn("🔊 فك كتم قروب/قناة", "unmute_chat_user")],
        [btn("👥 المكتومون في الخاص", "muted_list")],
        [btn("👀 سجل دخول البوت", "bot_access_log:0")],
        [btn("👤 إعدادات التقليد", "mimic_settings")],
        [btn("🧠 القواعد والأتمتة", "rules")],
        [btn("📋 سجل العمليات", "operation_log")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def private_menu():
    return kb([
        [btn("👥 الأشخاص في الخاص", "private_people:0")],
        [btn("🔄 جلب كل المستخدمين بالخاص", "sync_private_users")],
        [btn("📥 استيراد الرسائل", "import_messages")],
        [btn("🔎 بحث عن شخص", "private_search")],
        [btn("🗑️ مسح الأشخاص في الخاص", "private_delete_menu")],
        [btn("📊 إحصائيات المحادثات", "stats")],
        [btn("📢 استثناءات الإذاعة", "broadcast_exclusions")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def private_delete_menu():
    return kb([
        [btn("🗑️ تحديد مسح الجميع", "private_delete_all_confirm")],
        [btn("👤 مسح شخص بالـID أو المنشن", "private_delete_one")],
        [btn("🔙 إدارة الخاص", "private")],
    ])


def private_delete_all_confirm_menu():
    return kb([
        [btn("✅ نعم امسح الجميع", "private_delete_all_yes"), btn("❌ رفض", "private_delete_cancel")],
    ])


def storage_menu():
    return kb([
        [btn("📖 تصفح سجل المحادثات", "private_people:0")],
        [btn("💾 نسخ احتياطي كامل", "backup")],
        [btn("💾 نسخ احتياطي لمحادثة", "backup_choose")],
        [btn("🔎 البحث بالنص", "search_messages")],
        [btn("📋 سجل العمليات", "operation_log")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def important_menu():
    return kb([
        [btn("➕ حفظ رسالة مهمة", "important_add")],
        [btn("⭐ رسائلي المهمة", "important_list")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def broadcast_menu():
    return kb([
        [btn("📢 إرسال إذاعة", "broadcast_send")],
        [btn("🚫 استثناء شخص", "broadcast_exclude")],
        [btn("👥 المستثنون", "broadcast_exclusions")],
        [btn("📅 الإذاعات المجدولة", "broadcast_scheduled")],
        [btn("📊 سجل الإذاعات", "broadcast_log")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def broadcast_confirm_menu():
    return kb([[btn("✅ نعم أرسل", "broadcast_confirm_send"), btn("❌ إلغاء", "broadcast_cancel")]])


def protection_menu():
    return kb([
        [btn("🛡️ الحماية من نقل الملكية", "ownership_protection")],
        [btn("🖼️ فحص الوسائط", "media_protection")],
        [btn("📋 سجل الحماية", "security_log")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def settings_menu():
    return kb([
        [btn("🤖 الذكاء الاصطناعي", "ai_settings")],
        [btn("🔔 إعدادات التنبيهات", "notification_settings")],
        [btn("💾 إعدادات النسخ الاحتياطي", "backup_settings")],
        [btn("🛡️ إعدادات الحماية", "protection")],
        [btn("⚙️ إعدادات عامة", "general_settings")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def mimic_menu(settings: dict):
    def mark(key):
        return "🟢" if settings.get(key, "1") == "1" else "🔴"
    return kb([
        [btn(f"{mark('mimic_enabled')} تفعيل التقليد", "mimic_toggle")],
        [btn(f"{mark('mimic_name')} تقليد الاسم", "mimic_toggle:name"), btn(f"{mark('mimic_photo')} تقليد الصورة", "mimic_toggle:photo")],
        [btn(f"{mark('mimic_bio')} تقليد البايو", "mimic_toggle:bio")],
        [btn("💾 حفظ بياناتي الأصلية", "mimic_save_original")],
        [btn("↩️ استعادة بياناتي الأصلية", "mimic_restore")],
        [btn("🔙 الأتمتة", "automation")],
    ])


def ai_menu(enabled: bool, trigger: str):
    status = "🟢 يعمل" if enabled else "🔴 مغلق"
    trigger_text = trigger or "سبيشل فقط"
    return kb([
        [btn(f"{status} — تبديل", "ai_toggle")],
        [btn("✏️ إضافة اسم للذكاء", "ai_set_trigger"), btn("🗑️ حذف الاسم", "ai_clear_trigger")],
        [btn("📜 سجل الأسئلة والأجوبة", "ai_logs")],
        [btn("🔙 الإعدادات", "settings")],
    ])


def access_menu():
    return kb([
        [btn("➕ إضافة شخص مسموح", "access_add")],
        [btn("👥 المستخدمون المسموحون", "access_list")],
        [btn("🚫 المحظورون", "blocked_list")],
        [btn("🔓 إلغاء حظر شخص", "access_unban")],
        [btn("🗑️ إزالة مستخدم", "access_remove")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def durations_menu(prefix="duration"):
    return kb([
        [btn("🟢 يوم", f"{prefix}:1")],
        [btn("🔵 3 أيام", f"{prefix}:3")],
        [btn("🟣 أسبوع", f"{prefix}:7")],
        [btn("🟡 شهر", f"{prefix}:30")],
        [btn("🟠 شهرين", f"{prefix}:60")],
        [btn("🔴 3 أشهر", f"{prefix}:90")],
        [btn("♾️ مدى الحياة", f"{prefix}:life")],
        [btn("🔙 رجوع", "access")],
    ])


def back(callback="main_menu"):
    return kb([[btn("🔙 رجوع", callback)]])


def feature_permissions_menu(user_id, permissions, page=0, per_page=10):
    total = len(FEATURES); start = page * per_page; end = min(start + per_page, total)
    rows = []
    for key, label in FEATURES[start:end]:
        ok = permissions.get(key, True)
        rows.append([btn(f"{'🟢' if ok else '🔴'} {label}", f"fp:{user_id}:{key}:{page}")])
    nav = []
    if page > 0: nav.append(btn("⬅️ السابق", f"fpp:{user_id}:{page - 1}"))
    if end < total: nav.append(btn("التالي ➡️", f"fpp:{user_id}:{page + 1}"))
    if nav: rows.append(nav)
    rows.append([btn("✅ السماح بكل الميزات", f"fpa:{user_id}:1"), btn("🚫 منع الكل", f"fpa:{user_id}:0")])
    rows.append([btn("🔙 المستخدم", f"access_user:{user_id}")])
    return kb(rows)
