from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.core.permissions import FEATURES


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def btn(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu(user_id=None, allowed=None, logged_in=True):
    if allowed is None:
        allowed = {k: True for k, _ in FEATURES}
    def any_cat(cat):
        return any(allowed.get(k, False) for k, _ in FEATURES if k.startswith(cat + "."))
    rows = []
    if not logged_in:
        rows.append([btn("🔐 تسجيل حسابي", "account_login")])
    if any_cat("automation"):
        rows.append([btn("🧠 User Automation  ✨", "automation")])
    if any_cat("private"):
        rows.append([btn("📥 إدارة الخاص  💫", "private")])
    if any_cat("storage"):
        rows.append([btn("🗃 التخزين والنسخ  💾", "storage")])
    if any_cat("important"):
        rows.append([btn("⭐ الرسائل المهمة  🌟", "important")])
    if any_cat("broadcast"):
        rows.append([btn("📢 الإذاعة  🚀", "broadcast")])
    if any_cat("protection"):
        rows.append([btn("🛡️ مركز الحماية  🔒", "protection")])
    if any_cat("stats"):
        rows.append([btn("📊 إحصائيات الحساب  📈", "stats")])
    if any_cat("music"):
        rows.append([btn("🎵 استوديو الموسيقى  🎧", "music")])
    rows.append([btn("👤 حسابي  ⚡", "account")])
    rows.append([btn("⚙️ الإعدادات  ✨", "settings")])
    if user_id is None:
        rows.append([btn("👑 لوحة المطور 🛠️", "developer_panel")])
        rows.append([btn("👥 إدارة المستخدمين", "access")])
        rows.append([btn("🤖 الذكاء الاصطناعي", "ai_settings")])
    return kb(rows)


def automation_menu(owner=False):
    return kb([
        [btn("🧹 أوامر المسح والكتم", "private_commands")],
        [btn("🔇 كتم مستخدم", "mute_user"), btn("🔊 إلغاء الكتم", "unmute_user")],
        [btn("👥 قائمة المكتومين", "muted_list")],
        [btn("👤 إعدادات التقليد", "mimic_settings")],
        *([[btn("👀 سجل دخول البوت", "bot_access_log:0")]] if owner else []),
        [btn("📋 سجل العمليات", "operation_log")],
        [btn("🔄 فحص النظام", "runtime_refresh")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def private_menu():
    return kb([
        [btn("👥 الأشخاص في الخاص", "private_people:0")],
        [btn("🔄 مزامنة المستخدمين", "sync_private_users")],
        [btn("📥 استيراد الرسائل القديمة", "import_messages")],
        [btn("🔎 بحث متقدم", "private_search")],
        [btn("📊 إحصائيات المحادثات", "stats")],
        [btn("🚫 استثناءات الإذاعة", "broadcast_exclusions")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def storage_menu():
    return kb([
        [btn("📖 تصفح سجل المحادثات", "private_people:0")],
        [btn("💾 نسخ احتياطي كامل", "backup")],
        [btn("💾 نسخ احتياطي لمحادثة", "backup_choose")],
        [btn("🔎 البحث في التخزين", "search_messages")],
        *([[btn("👀 سجل دخول البوت", "bot_access_log:0")]] if owner else []),
        [btn("📋 سجل العمليات", "operation_log")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def important_menu():
    return kb([[btn("➕ حفظ رسالة مهمة", "important_add")], [btn("⭐ رسائلي المهمة", "important_list")], [btn("🔙 الرئيسية", "main_menu")]])


def broadcast_menu():
    return kb([
        [btn("📢 إرسال إذاعة", "broadcast_send")],
        [btn("🚫 استثناء شخص", "broadcast_exclude"), btn("👥 المستثنون", "broadcast_exclusions")],
        [btn("📅 المجدولة", "broadcast_scheduled"), btn("📜 السجل", "broadcast_log")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def broadcast_confirm_menu():
    return kb([[btn("🚀 نعم أرسل", "broadcast_confirm_send"), btn("❌ إلغاء", "broadcast_cancel")]])


def protection_menu():
    return kb([
        [btn("🛡️ حماية نقل الملكية", "ownership_protection")],
        [btn("📋 سجل الحماية", "security_log")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def settings_menu():
    return kb([
        [btn("🤖 الذكاء الاصطناعي ✨", "ai_settings")],
        [btn("🔔 التنبيهات 🔔", "notification_settings")],
        [btn("💾 النسخ الاحتياطي 💾", "backup_settings")],
        [btn("🛡️ الحماية 🛡️", "protection")],
        [btn("👤 حسابي 👤", "account")],
        [btn("⚙️ عامة ⚙️", "general_settings")],
        [btn("🔙 الرئيسية 🏠", "main_menu")],
    ])

def music_menu():
    return kb([
        [btn("🔎 البحث عن صوت 🎧", "music_search")],
        [btn("📚 آخر النتائج 🎼", "music_results")],
        [btn("🔙 الرئيسية 🏠", "main_menu")],
    ])

def music_results_menu(results):
    rows = [[btn(f"🎵 {str(r.get('title') or r.get('identifier'))[:48]}", f"music_get:{r.get('identifier')}")] for r in results]
    rows.append([btn("🔎 بحث جديد 🔍", "music_search")])
    rows.append([btn("🔙 الموسيقى 🎧", "music")])
    return kb(rows)

def developer_menu():
    return kb([
        [btn("👥 إدارة المستخدمين 👥", "access")],
        [btn("🔍 فحص صلاحيات مستخدم 🔎", "dev_permission_search")],
        [btn("📊 إحصائيات البوت 📈", "dev_stats")],
        [btn("👀 سجل دخول البوت 👀", "bot_access_log:0")],
        [btn("📋 سجل العمليات 📋", "operation_log")],
        [btn("🩺 صحة النظام 🩺", "runtime_refresh")],
        [btn("🔐 مركز الأمان 🔐", "dev_security")],
        [btn("🔄 إدارة الحسابات 🔄", "dev_accounts")],
        [btn("🔙 الرئيسية 🏠", "main_menu")],
    ])


def account_menu(status=False):
    return kb([
        [btn("🟢 حالة الحساب" if status else "🔴 الحساب غير متصل", "account_status")],
        [btn("🔐 تسجيل حسابي", "account_login")],
        [btn("🚪 تسجيل خروج الحساب", "account_logout")],
        [btn("🔐 مركز الأمان", "security_center")],
        [btn("🔄 تبديل/إدارة الحساب", "account_switch")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def mimic_menu(settings: dict):
    def mark(key): return "🟢" if settings.get(key, "1") == "1" else "🔴"
    return kb([
        [btn(f"{mark('mimic_enabled')} تشغيل التقليد", "mimic_toggle")],
        [btn(f"{mark('mimic_name')} الاسم", "mimic_toggle:name"), btn(f"{mark('mimic_photo')} الصورة", "mimic_toggle:photo")],
        [btn(f"{mark('mimic_bio')} البايو", "mimic_toggle:bio"), btn(f"{mark('mimic_username')} يوزر مشابه", "mimic_toggle:username")],
        [btn(f"{mark('mimic_location')} الموقع", "mimic_toggle:location")],
        [btn("💾 حفظ الأصل", "mimic_save_original"), btn("↩️ استعادة الأصل", "mimic_restore")],
        [btn("🔙 الأتمتة", "automation")],
    ])


def ai_menu(enabled: bool, trigger: str):
    return kb([
        [btn(("🟢" if enabled else "🔴") + " الذكاء — تبديل", "ai_toggle")],
        [btn("✏️ إضافة اسم", "ai_set_trigger"), btn("🗑️ حذف الاسم", "ai_clear_trigger")],
        [btn("📜 سجل الأسئلة", "ai_logs")],
        [btn("🔙 الإعدادات", "settings")],
    ])


def access_menu():
    return kb([
        [btn("➕ إضافة مستخدم", "access_add")],
        [btn("👥 المستخدمون المسموحون", "access_list")],
        [btn("🗑️ إزالة مستخدم", "access_remove")],
        [btn("🔙 الرئيسية", "main_menu")],
    ])


def durations_menu(prefix="duration"):
    return kb([
        [btn("🟢 يوم", f"{prefix}:1"), btn("🔵 3 أيام", f"{prefix}:3")],
        [btn("🟣 أسبوع", f"{prefix}:7"), btn("🟡 شهر", f"{prefix}:30")],
        [btn("🟠 شهرين", f"{prefix}:60"), btn("🔴 3 أشهر", f"{prefix}:90")],
        [btn("♾️ مدى الحياة", f"{prefix}:life")],
        [btn("🔙 رجوع", "access")],
    ])


def back(callback="main_menu"):
    return kb([[btn("🔙 رجوع", callback)]])


def feature_permissions_menu(user_id, permissions, page=0, per_page=10):
    total = len(FEATURES); start = page * per_page; end = min(start + per_page, total)
    rows = [[btn(f"{'🟢' if permissions.get(key, True) else '🔴'} {label}", f"fp:{user_id}:{key}:{page}")] for key, label in FEATURES[start:end]]
    nav = []
    if page > 0: nav.append(btn("⬅️ السابق", f"fpp:{user_id}:{page-1}"))
    if end < total: nav.append(btn("التالي ➡️", f"fpp:{user_id}:{page+1}"))
    if nav: rows.append(nav)
    rows.append([btn("✅ السماح بكل شيء", f"fpa:{user_id}:1"), btn("🚫 منع الكل", f"fpa:{user_id}:0")])
    rows.append([btn("🔙 المستخدم", f"access_user:{user_id}")])
    return kb(rows)
