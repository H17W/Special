from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile

from app.core.config import ADMIN_ID
from app.core.database import *
from app.core.permissions import FEATURES
from app.core.exporter import create_full_backup, create_chat_backup
from app.user.moderation import muted_users
from app.user.client import client as user_client, active_client, import_all_private_history, refresh_special, sync_all_private_users, get_or_create_user_client, set_active_client
from .handlers import waiting_for_mute, waiting_for_unmute, waiting_for_chat_mute, waiting_for_chat_unmute, pending
from .keyboards import *

router = Router()

SECTION_KEYS = {"automation":"automation.monitor","private":"private.people","storage":"storage.backup","important":"important.add","broadcast":"broadcast.create","protection":"protection.media_scan","stats":"stats.people","settings":"settings.general"}
ACTION_KEYS = {
    "mute_private_user":"automation.mute","unmute_private_user":"automation.unmute","mute_chat_user":"automation.mute","unmute_chat_user":"automation.unmute","runtime_refresh":"automation.monitor","muted_list":"automation.muted_list","bot_access_log":"automation.monitor","mimic_settings":"automation.monitor","mimic_toggle":"automation.monitor","mimic_save_original":"automation.monitor","mimic_restore":"automation.monitor","rules":"automation.rules","operation_log":"log.operations",
    "private_people":"private.people","sync_private_users":"private.people","import_messages":"private.import","private_search":"private.people","private_delete_menu":"private.people","private_delete_all_confirm":"private.people","private_delete_all_yes":"private.people","private_delete_cancel":"private.people","private_delete_one":"private.people","search_messages":"private.search","stats":"stats.people",
    "backup":"storage.backup","backup_choose":"storage.backup","storage_chats":"storage.browse","storage_chat":"storage.browse","backup_chat_search":"storage.backup","important_add":"important.add","important_list":"important.list",
    "broadcast_send":"broadcast.create","broadcast_confirm_send":"broadcast.send","broadcast_exclude":"broadcast.exclude","broadcast_exclusions":"broadcast.exclusions","broadcast_log":"broadcast.log","broadcast_scheduled":"broadcast.schedule",
    "ownership_protection":"protection.ownership","ownership_toggle":"protection.ownership","media_protection":"protection.media_scan","security_log":"protection.log","notification_settings":"notifications.settings","backup_settings":"settings.backup","general_settings":"settings.general",
    "ai_settings":"ai.settings","ai_toggle":"ai.toggle","ai_logs":"ai.logs","ai_set_trigger":"ai.trigger","ai_clear_trigger":"ai.trigger",
    "blocked_list":"access.manage","access_unban":"access.manage",
}


def is_admin(uid):
    return bool(ADMIN_ID and str(uid) == str(ADMIN_ID))


def user_id(c):
    return c.from_user.id if c.from_user else 0


def feature_allowed(uid, key):
    if is_admin(uid):
        return True
    r = get_allowed_user(uid)
    if not r or r['status'] != 'active':
        return False
    return is_feature_enabled(uid, key) if '.' in key else any(is_feature_enabled(uid, k) for k, _ in FEATURES if k.startswith(key + '.'))


async def guard(c, key=None, owner_only=False):
    uid = user_id(c)
    if get_setting("bot_paused", "0") == "1":
        await c.answer('⏸️ البوت موقوف مؤقتًا. اكتب تفعيل داخل البوت لإعادته.', show_alert=True)
        return False
    if owner_only:
        if not is_admin(uid):
            await c.answer('⛔ هذه اللوحة للمالك فقط.', show_alert=True)
            return False
        try:
            set_active_client(user_client, uid)
        except Exception:
            pass
        return True
    if not is_admin(uid):
        r = get_allowed_user(uid)
        if not r or r['status'] != 'active':
            await c.answer('⛔ لا تملك صلاحية استخدام Special.', show_alert=True)
            return False
    try:
        set_active_client(await get_or_create_user_client(uid), uid)
    except Exception:
        pass
    if key and not feature_allowed(uid, key):
        await c.answer('🚫 هذه الميزة ممنوعة عن حسابك.', show_alert=True)
        return False
    return True


async def show(c, text, markup):
    try:
        await c.message.edit_text(text, reply_markup=markup)
    except Exception:
        await c.message.answer(text, reply_markup=markup)
    await c.answer()


@router.callback_query(F.data == 'main_menu')
async def main(c):
    if not await guard(c):
        return
    uid = user_id(c)
    await show(c, '🧠 أهلاً بك في Special\n\nلوحة التحكم الرئيسية:', main_menu(None) if is_admin(uid) else main_menu(uid, get_feature_permissions(uid)))


@router.callback_query(F.data == 'automation')
async def automation(c):
    if await guard(c, 'automation'):
        await show(c, f'🧠 User Automation\n\n🔇 المكتومون: {len(muted_users())}', automation_menu())


@router.callback_query(F.data.startswith('bot_access_log'))
async def bot_access_history(c):
    if not await guard(c, 'automation.monitor', owner_only=True):
        return
    parts = c.data.split(':')
    page = max(0, int(parts[1]) if len(parts) > 1 else 0)
    per_page = 5
    rows = list_bot_access_logs(per_page, page * per_page)
    total = count_bot_access_logs()
    if not rows:
        await show(c, '👀 لا يوجد سجل دخول محفوظ حاليًا.', InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🧹 تصفية سجل الدخول', callback_data='clear_bot_access_log')],[InlineKeyboardButton(text='🔙 الأتمتة', callback_data='automation')]]))
        return
    lines = ['👀 سجل دخول بوت Special', f'صفحة {page+1} — الإجمالي {total}', '']
    for r in rows:
        status = '✅ مسموح' if r['status'] == 'allowed' else '⛔ مرفوض'
        username = f"@{r['username']}" if r['username'] else 'بدون يوزر'
        lines.append(f"{status}\n👤 {r['display_name'] or 'مستخدم'}\n🆔 {r['user_id']}\n🔗 {username}\n🕐 {r['created_at']}")
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='⬅️ السابق', callback_data=f'bot_access_log:{page-1}'))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton(text='التالي ➡️', callback_data=f'bot_access_log:{page+1}'))
    rows_kb = [nav] if nav else []
    rows_kb.append([InlineKeyboardButton(text='🧹 تصفية سجل الدخول', callback_data='clear_bot_access_log')])
    rows_kb.append([InlineKeyboardButton(text='🔙 الأتمتة', callback_data='automation')])
    await show(c, '\n\n'.join(lines)[:3900], InlineKeyboardMarkup(inline_keyboard=rows_kb))


@router.callback_query(F.data == 'clear_bot_access_log')
async def clear_bot_access_log_cb(c):
    if not await guard(c, owner_only=True):
        return
    clear_bot_access_logs()
    await show(c, '🧹 تم تصفية سجل دخول البوت بالكامل.', automation_menu())


@router.callback_query(F.data == 'mimic_settings')
async def mimic_settings(c):
    if not await guard(c, 'automation.monitor', owner_only=True):
        return
    settings = {k: get_setting(k, '1') for k in ['mimic_enabled','mimic_name','mimic_photo','mimic_bio']}
    text = (
        '👤 إعدادات التقليد\n\n'
        f"التقليد: {'🟢 يعمل' if settings['mimic_enabled']=='1' else '🔴 متوقف'}\n"
        f"الاسم: {'🟢' if settings['mimic_name']=='1' else '🔴'}\n"
        f"الصورة: {'🟢' if settings['mimic_photo']=='1' else '🔴'}\n"
        f"البايو: {'🟢' if settings['mimic_bio']=='1' else '🔴'}\n\n"
        'التقليد هنا يقتصر على الاسم والصورة والبايو فقط.\n'
        'لن يتم تغيير اليوزر أو الموقع.'
    )
    await show(c, text, mimic_menu(settings))


@router.callback_query(F.data == 'mimic_toggle')
async def mimic_toggle(c):
    if not await guard(c, 'automation.monitor', owner_only=True):
        return
    cur = get_setting('mimic_enabled', '1') == '1'
    set_setting('mimic_enabled', '0' if cur else '1')
    await mimic_settings(c)


@router.callback_query(F.data.startswith('mimic_toggle:'))
async def mimic_toggle_field(c):
    if not await guard(c, 'automation.monitor', owner_only=True):
        return
    keymap = {'name':'mimic_name','photo':'mimic_photo','bio':'mimic_bio'}
    key = keymap.get(c.data.split(':',1)[1])
    if not key:
        await c.answer('إعداد غير معروف', show_alert=True); return
    cur = get_setting(key, '1') == '1'
    set_setting(key, '0' if cur else '1')
    await mimic_settings(c)


@router.callback_query(F.data == 'mimic_save_original')
async def mimic_save_original(c):
    if not await guard(c, 'automation.monitor', owner_only=True):
        return
    try:
        from app.user.client import _backup_current_profile
        await _backup_current_profile()
        await c.answer('✅ تم حفظ بيانات حسابك الأصلية', show_alert=True)
    except Exception as exc:
        await c.answer(f'❌ فشل الحفظ: {type(exc).__name__}', show_alert=True)


@router.callback_query(F.data == 'mimic_restore')
async def mimic_restore(c):
    if not await guard(c, 'automation.monitor', owner_only=True):
        return
    try:
        from app.user.client import restore_profile
        ok = await restore_profile()
        await c.answer('✅ تمت الاستعادة' if ok else 'ℹ️ لا توجد نسخة أصلية محفوظة', show_alert=True)
        await mimic_settings(c)
    except Exception as exc:
        await c.answer(f'❌ فشل الاستعادة: {type(exc).__name__}', show_alert=True)


@router.callback_query(F.data == 'private_commands')
async def private_commands(c):
    if not await guard(c, 'automation'):
        return
    text = (
        '📖 أوامر المسح والكتم والتقليد\n\n'
        '🗑️ /بداية — رد على أول رسالة تريد المسح منها\n'
        '🗑️ /نهاية — رد على آخر رسالة تريد المسح إليها\n'
        '🔇 كتم — رد على رسالة الشخص\n'
        '🔊 الغاء الكتم — رد على رسالة الشخص\n'
        '👤 تقليد — رد على مستخدم أو قروب أو قناة\n'
        '↩️ الغاء التقليد — استعادة حسابك\n'
        '🔄 تحديث — فحص الاتصال والبيانات وتحديث التقليد\n\n'
        'تعمل أوامر المسح والكتم والتقليد في أي مكان تسمح فيه صلاحيات حسابك بتنفيذ العملية.'
    )
    await show(c, text, back('automation'))


@router.callback_query(F.data == 'runtime_refresh')
async def runtime_refresh(c):
    if not await guard(c, 'automation'):
        return
    try:
        result = await refresh_special()
        msg = '✅ تم تحديث البوت بنجاح\n\n'
        msg += '🖼️ تم تحديث بيانات وصورة التقليد الحالي.' if result.get('mimic_refreshed') else '🟢 تم فحص الاتصال وقاعدة البيانات وقائمة الخاص.'
        await show(c, msg, automation_menu())
    except Exception as exc:
        await c.message.answer(f'❌ تعذر تحديث البوت: {type(exc).__name__}')
        await c.answer()


@router.callback_query(F.data == 'mute_private_user')
async def mute_private_cb(c):
    if await guard(c, 'automation.mute'):
        waiting_for_mute.add(user_id(c))
        await show(c, '🔇 كتم مستخدم في الخاص\n\nأرسل Telegram ID أو @username للمستخدم.', back('automation'))


@router.callback_query(F.data == 'unmute_private_user')
async def unmute_private_cb(c):
    if await guard(c, 'automation.unmute'):
        waiting_for_unmute.add(user_id(c))
        await show(c, '🔊 إلغاء كتم من الخاص\n\nأرسل Telegram ID أو @username للمستخدم.', back('automation'))


@router.callback_query(F.data == 'mute_chat_user')
async def mute_chat_cb(c):
    if await guard(c, 'automation.mute'):
        waiting_for_chat_mute[user_id(c)] = None
        await show(c, '🔇 كتم مستخدم في قروب/قناة\n\nالخطوة 1 من 2\nأرسل Chat ID للقروب أو القناة.', back('automation'))


@router.callback_query(F.data == 'unmute_chat_user')
async def unmute_chat_cb(c):
    if await guard(c, 'automation.unmute'):
        waiting_for_chat_unmute[user_id(c)] = None
        await show(c, '🔊 إلغاء كتم من قروب/قناة\n\nالخطوة 1 من 2\nأرسل Chat ID للقروب أو القناة.', back('automation'))


@router.callback_query(F.data == 'muted_list')
async def muted(c):
    if not await guard(c, 'automation.muted_list'):
        return
    rows = muted_users()
    text = '👥 المكتومون\n\n' + ('لا يوجد مستخدمون مكتومون.' if not rows else '\n'.join(f"🔇 {r['display_name'] or 'مستخدم'} | ID: {r['user_id']}" for r in rows))
    await show(c, text, back('automation'))


@router.callback_query(F.data == 'private')
async def private(c):
    if await guard(c, 'private'):
        await show(c, '📥 إدارة الخاص\n\nإدارة الأشخاص والمحادثات المحفوظة.', private_menu())


@router.callback_query(F.data == 'private_delete_menu')
async def private_delete_menu_cb(c):
    if await guard(c, 'private.people'):
        await show(c, '🗑️ مسح الأشخاص في الخاص\n\nهذا المسح يحذف البيانات المحفوظة داخل Special فقط ولا يحذف أي شيء من Telegram.', private_delete_menu())


@router.callback_query(F.data == 'private_delete_all_confirm')
async def private_delete_all_confirm_cb(c):
    if await guard(c, 'private.people'):
        count = private_chats_count()
        await show(c, f'⚠️ تأكيد مسح جميع الأشخاص في الخاص\n\nسيتم حذف الأشخاص المحفوظين في Special مع رسائلهم وبياناتهم المحلية.\n\nالعدد الحالي: {count}\n\nهل أنت متأكد؟', private_delete_all_confirm_menu())


@router.callback_query(F.data == 'private_delete_all_yes')
async def private_delete_all_yes_cb(c):
    if not await guard(c, 'private.people'):
        return
    count = delete_all_private_people()
    await show(c, f'✅ تم مسح الأشخاص في الخاص من Special فقط\n\n🗑️ تم حذف: {count} شخص', private_menu())


@router.callback_query(F.data == 'private_delete_cancel')
async def private_delete_cancel_cb(c):
    if await guard(c, 'private.people'):
        await show(c, '↩️ تم إلغاء عملية المسح.', private_delete_menu())


@router.callback_query(F.data == 'private_delete_one')
async def private_delete_one_cb(c):
    if not await guard(c, 'private.people'):
        return
    pending[user_id(c)] = {'action': 'private_delete_one'}
    await show(c, '👤 مسح شخص من الخاص\n\nأرسل Telegram ID أو @username للشخص.\n\n⚠️ سيتم حذفه من قاعدة بيانات Special فقط ولن يتم حظره أو حذفه من Telegram.', back('private'))


@router.callback_query(F.data == 'sync_private_users')
async def sync_private_users_cb(c):
    if not await guard(c, 'private.people'):
        return
    await c.message.edit_text('🔄 جاري جلب جميع المستخدمين الحقيقيين من الخاص...')
    try:
        result = await sync_all_private_users()
        await c.message.answer(f"✅ تم تحديث قائمة الخاص\n\n➕ المضافون: {result['added']}\n🔄 المحدثون: {result['updated']}\n⏭️ المتجاهلون: {result['skipped']}", reply_markup=private_menu())
    except Exception as exc:
        await c.message.answer(f'❌ تعذر جلب المستخدمين: {type(exc).__name__}', reply_markup=private_menu())
    await c.answer()


@router.callback_query(F.data == 'import_messages')
async def import_messages(c):
    if not await guard(c, 'private.import'):
        return
    # Answer the callback immediately. Importing history can take longer than
    # Telegram's callback-query response window, so waiting until the end can
    # produce: "query is too old and response timeout expired".
    try:
        await c.answer('⏳ بدأ الاستيراد')
    except Exception:
        pass
    await c.message.edit_text('📥 جاري استيراد الرسائل القديمة من الخاص فقط...\n\nلا يتم استيراد البوتات أو القروبات أو القنوات ولا يتم تحميل الوسائط أثناء الاستيراد.')
    try:
        result = await import_all_private_history()
        await c.message.answer('✅ تم استيراد الرسائل بنجاح\n\n' f"👥 المحادثات: {result['chats']}\n💬 الرسائل الجديدة: {result['messages']}\n⏭️ الرسائل الموجودة مسبقًا: {result['skipped']}", reply_markup=private_menu())
    except Exception as exc:
        await c.message.answer(f'❌ تعذر استيراد الرسائل: {type(exc).__name__}', reply_markup=private_menu())


@router.callback_query(F.data == 'private_search')
async def private_search(c):
    if await guard(c, 'private.people'):
        pending[user_id(c)] = {'action': 'private_search'}
        await show(c, '🔎 أرسل الاسم أو @username أو Telegram ID للبحث في الأشخاص الحقيقيين في الخاص.', back('private'))


@router.callback_query(F.data.startswith('storage_chats:'))
async def storage_chats(c):
    if not await guard(c, 'storage.browse'):
        return
    page = int(c.data.split(':')[1])
    rows, total = private_chats_page(page, 10)
    buttons = [[InlineKeyboardButton(text=f"👤 {r['display_name'] or r['user_id']}", callback_data=f"storage_chat:{r['user_id']}")] for r in rows]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='⬅️ السابق', callback_data=f'storage_chats:{page-1}'))
    if (page + 1) * 10 < total:
        nav.append(InlineKeyboardButton(text='التالي ➡️', callback_data=f'storage_chats:{page+1}'))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text='🔙 التخزين والنسخ الاحتياطي', callback_data='storage')])
    await show(c, f'📖 تصفح سجل المحادثات\n\nصفحة {page+1} — الإجمالي {total}', InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith('storage_chat:'))
async def storage_chat(c):
    if not await guard(c, 'storage.browse'):
        return
    uid = int(c.data.split(':', 1)[1])
    r = get_private_chat(uid)
    if not r:
        await c.answer('المحادثة غير موجودة', show_alert=True)
        return
    text = f"👤 {r['display_name'] or 'مستخدم'}\n🆔 ID: {uid}\n🔗 Username: {('@'+r['username']) if r['username'] else 'لا يوجد يوزر'}\n\n💬 الرسائل: {r['message_count']}\n🖼 الصور: {r['photo_count']}\n🎥 الفيديوهات: {r['video_count']}\n🃏 الملصقات: {r['sticker_count']}\n🎞 GIF: {r['gif_count']}\n🔗 الروابط: {r['link_count']}"
    await show(c, text, kb([[InlineKeyboardButton(text='📖 تصفح السجل', callback_data=f'browse:{uid}:0')],[InlineKeyboardButton(text='💾 نسخ احتياطي', callback_data=f'backup:{uid}')],[InlineKeyboardButton(text='🔙 التخزين والنسخ الاحتياطي', callback_data='storage')]]))


@router.callback_query(F.data.startswith('private_people:'))
async def private_people(c):
    if not await guard(c, 'private.people'):
        return
    page = int(c.data.split(':')[1])
    rows, total = private_chats_page(page, 10)
    buttons = [[InlineKeyboardButton(text=f"👤 {r['display_name'] or r['user_id']}", callback_data=f"chat:{r['user_id']}")] for r in rows]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='⬅️ السابق', callback_data=f'private_people:{page-1}'))
    if (page + 1) * 10 < total:
        nav.append(InlineKeyboardButton(text='التالي ➡️', callback_data=f'private_people:{page+1}'))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text='🔎 بحث', callback_data='private_search')])
    buttons.append([InlineKeyboardButton(text='🔙 إدارة الخاص', callback_data='private')])
    await show(c, f'👥 الأشخاص في الخاص\n\nصفحة {page+1} — الإجمالي {total}', InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith('chat:'))
async def chat(c):
    if not await guard(c, 'private.open_chat'):
        return
    uid = int(c.data.split(':', 1)[1])
    r = get_private_chat(uid)
    if not r:
        await c.answer('المحادثة غير موجودة', show_alert=True)
        return
    text = f"👤 {r['display_name'] or 'مستخدم'}\n🆔 ID: {uid}\n🔗 Username: {('@'+r['username']) if r['username'] else 'لا يوجد يوزر'}\n\n💬 الرسائل: {r['message_count']}\n🖼 الصور: {r['photo_count']}\n🎥 الفيديوهات: {r['video_count']}\n🃏 الملصقات: {r['sticker_count']}\n🎞 GIF: {r['gif_count']}\n🔗 الروابط: {r['link_count']}"
    await show(c, text, kb([[InlineKeyboardButton(text='📖 تصفح السجل', callback_data=f'browse:{uid}:0')],[InlineKeyboardButton(text='💾 نسخ احتياطي', callback_data=f'backup:{uid}')],[InlineKeyboardButton(text='🔙 الأشخاص', callback_data='private_people:0')]]))


@router.callback_query(F.data.startswith('browse:'))
async def browse(c):
    if not await guard(c, 'storage.browse'):
        return
    _, uid, offset = c.data.split(':')
    rows = list_messages(int(uid), 10, int(offset))
    if not rows:
        await show(c, '📖 لا توجد رسائل محفوظة.', back(f'chat:{uid}'))
        return
    chat_row = get_private_chat(int(uid))
    other_name = (chat_row['display_name'] if chat_row else None) or 'الشخص'
    lines = ['📖 سجل المحادثة', '']
    previous_day = None
    month_names = {
        1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل', 5: 'مايو', 6: 'يونيو',
        7: 'يوليو', 8: 'أغسطس', 9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
    }
    saudi_tz = timezone(timedelta(hours=3))
    for r in rows:
        raw_date = r['message_date'] or ''
        try:
            dt = datetime.fromisoformat(str(raw_date).replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(saudi_tz)
            day_key = dt.date()
            if day_key != previous_day:
                if len(lines) > 2:
                    lines.append('')
                lines.append(f"{dt.day} {month_names[dt.month]} {dt.year}")
                previous_day = day_key
            time_text = dt.strftime('%H:%M')
        except Exception:
            time_text = str(raw_date)[:16] if raw_date else '--:--'
        sender_name = 'أنت' if r['direction'] == 'outgoing' else other_name
        body = r['text'] or f"[{r['media_type'] or 'وسائط'}]"
        lines.append(f"{sender_name} {time_text}")
        lines.append(body)
        lines.append('')
    nav = []
    if int(offset) > 0:
        nav.append(InlineKeyboardButton(text='⬅️ الأقدم', callback_data=f'browse:{uid}:{max(0,int(offset)-10)}'))
    if len(rows) == 10:
        nav.append(InlineKeyboardButton(text='الأحدث ➡️', callback_data=f'browse:{uid}:{int(offset)+10}'))
    rows_kb = [nav] if nav else []
    rows_kb.append([InlineKeyboardButton(text='🔙 المحادثة', callback_data=f'storage_chat:{uid}')])
    await show(c, '\n'.join(lines), InlineKeyboardMarkup(inline_keyboard=rows_kb))


@router.callback_query(F.data == 'storage')
async def storage(c):
    if await guard(c, 'storage'):
        await show(c, '🗃 التخزين والنسخ الاحتياطي', storage_menu())


@router.callback_query(F.data == 'backup')
async def backup(c):
    if not await guard(c, 'storage.backup'):
        return
    await c.answer('⏳ جاري إنشاء النسخة الاحتياطية')
    try:
        paths = create_full_backup()
        for index, path in enumerate(paths, 1):
            await c.message.answer_document(FSInputFile(path), caption=f'💾 النسخة الاحتياطية — الجزء {index}/3 — 33.333% تقريبًا من الحمولة')
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as exc:
        await c.message.answer(f'❌ فشل النسخ الاحتياطي: {type(exc).__name__}')


@router.callback_query(F.data == 'backup_choose')
async def backup_choose(c):
    if not await guard(c, 'storage.backup'):
        return
    rows = list_private_chats()
    buttons = [[InlineKeyboardButton(text=f"👤 {r['display_name'] or r['user_id']}", callback_data=f'backup:{r["user_id"]}')] for r in rows[:50]]
    buttons.append([InlineKeyboardButton(text='🔙 التخزين', callback_data='storage')])
    await show(c, '💾 اختر محادثة:', InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == 'backup_chat_search')
async def backup_chat_search(c):
    if not await guard(c, 'storage.backup'):
        return
    pending[user_id(c)] = {'action': 'backup_chat_search'}
    await show(c, '🔎 البحث عن محادثة للنسخ الاحتياطي\n\nأرسل Telegram ID أو @username للمحادثة المحفوظة في Special.', back('storage'))


@router.callback_query(F.data.startswith('backup:'))
async def backup_chat(c):
    if not await guard(c, 'storage.backup'):
        return
    uid = int(c.data.split(':', 1)[1])
    path = create_chat_backup(uid)
    if not path:
        await c.answer('المحادثة غير موجودة', show_alert=True)
        return
    await c.message.answer_document(FSInputFile(path), caption=f'💾 نسخة محادثة {uid}')
    await c.answer()


@router.callback_query(F.data == 'important')
async def important(c):
    if await guard(c, 'important'):
        await show(c, '⭐ الرسائل المهمة', important_menu())


@router.callback_query(F.data == 'important_add')
async def important_add(c):
    if await guard(c, 'important.add'):
        await show(c, '⭐ حفظ رسالة مهمة\n\nاستخدم أمر مهم بالرد على الرسالة في الخاص.', back('important'))


@router.callback_query(F.data == 'important_list')
async def important_list(c):
    if not await guard(c, 'important.list'):
        return
    rows = important_messages()
    text = '⭐ الرسائل المهمة\n\n' + ('لا توجد رسائل محفوظة.' if not rows else '\n\n'.join(f"🆔 {r['user_id']}\n📝 {r['text'] or '['+(r['media_type'] or 'وسائط')+']'}\n🕐 {r['message_date'] or ''}" for r in rows[:40]))
    await show(c, text, back('important'))


@router.callback_query(F.data == 'broadcast')
async def broadcast(c):
    if await guard(c, 'broadcast'):
        await show(c, f"📢 الإذاعة\n\n👥 المستهدفون من البشر الحقيقيين: {len(broadcast_targets())}\n🚫 المستثنون: {len(list_broadcast_exclusions())}", broadcast_menu())


@router.callback_query(F.data == 'broadcast_send')
async def broadcast_send(c):
    if await guard(c, 'broadcast.create'):
        pending[user_id(c)] = {'action': 'broadcast_text'}
        await show(c, '📢 أرسل نص الإذاعة الآن.', back('broadcast'))


@router.callback_query(F.data == 'broadcast_cancel')
async def broadcast_cancel(c):
    pending.pop(user_id(c), None)
    await show(c, '❌ تم إلغاء الإذاعة.', broadcast_menu())


@router.callback_query(F.data == 'broadcast_confirm_send')
async def broadcast_confirm_send(c):
    if not await guard(c, 'broadcast.send'):
        return
    state = pending.pop(user_id(c), None)
    if not state or state.get('action') != 'broadcast_confirm':
        await c.answer('لا توجد إذاعة معلقة', show_alert=True)
        return
    text = state.get('text', '').strip()
    targets = broadcast_targets()
    started = datetime.now(timezone.utc).isoformat(); sent = failed = 0
    await c.message.edit_text(f'📢 جاري الإرسال...\n\n👥 المستهدفون: {len(targets)}')
    for row in targets:
        try:
            await active_client().send_message(int(row['user_id']), text)
            sent += 1
        except Exception as exc:
            failed += 1
            add_log('operation_log', 'broadcast_failed', f"{row['user_id']}: {type(exc).__name__}")
    finished = datetime.now(timezone.utc).isoformat()
    add_broadcast_log(text, len(targets), sent, failed, started, finished)
    await c.message.answer(f'✅ انتهت الإذاعة\n\n👥 {len(targets)}\n✅ {sent}\n❌ {failed}', reply_markup=broadcast_menu())
    await c.answer()


@router.callback_query(F.data == 'broadcast_exclude')
async def broadcast_exclude(c):
    if await guard(c, 'broadcast.exclude'):
        pending[user_id(c)] = {'action': 'broadcast_exclude'}
        await show(c, '🚫 أرسل ID أو @username لشخص حقيقي في الخاص لاستثنائه.', back('broadcast'))


@router.callback_query(F.data == 'broadcast_exclusions')
async def broadcast_exclusions(c):
    if not await guard(c, 'broadcast.exclusions'):
        return
    rows = list_broadcast_exclusions()
    text = '🚫 المستثنون من الإذاعة\n\n' + ('لا يوجد مستثنون.' if not rows else '\n'.join(f"{r['display_name'] or r['user_id']} — {r['user_id']}" for r in rows))
    await show(c, text, back('broadcast'))


@router.callback_query(F.data == 'broadcast_log')
async def broadcast_log(c):
    if not await guard(c, 'broadcast.log'):
        return
    rows = list_broadcast_logs()
    text = '📊 سجل الإذاعات\n\n' + ('لا توجد إذاعات.' if not rows else '\n\n'.join(f"🕐 {r['started_at']}\n👥 {r['total_targets']} | ✅ {r['sent_count']} | ❌ {r['failed_count']}\n📝 {r['text'][:150]}" for r in rows))
    await show(c, text, back('broadcast'))


@router.callback_query(F.data == 'broadcast_scheduled')
async def broadcast_scheduled(c):
    if not await guard(c, 'broadcast.schedule'):
        return
    rows = list_scheduled_broadcasts()
    text = '📅 الإذاعات المجدولة\n\n' + ('لا توجد إذاعات مجدولة.' if not rows else '\n'.join(f"#{r['id']} — {r['run_at']} — {r['status']}" for r in rows))
    await show(c, text, back('broadcast'))


@router.callback_query(F.data == 'protection')
async def protection(c):
    if await guard(c, 'protection'):
        await show(c, '🛡 الحماية', protection_menu())


@router.callback_query(F.data == 'ownership_protection')
async def ownership(c):
    if not await guard(c, 'protection.ownership'):
        return
    enabled = get_setting('ownership_protection', '0') == '1'
    await show(c, f"🛡️ الحماية من نقل الملكية\n\nالحالة: {'🟢 مفعلة' if enabled else '🔴 غير مفعلة'}\n\nTelegram لا يوفر حدث رفض عام لنقل الملكية؛ الإعداد يسجل الحالة فقط.", kb([[InlineKeyboardButton(text='🟢 تفعيل' if not enabled else '🔴 تعطيل', callback_data='ownership_toggle')],[InlineKeyboardButton(text='📋 سجل الحماية', callback_data='security_log')],[InlineKeyboardButton(text='🔙 الحماية', callback_data='protection')]]))


@router.callback_query(F.data == 'ownership_toggle')
async def ownership_toggle(c):
    if not await guard(c, 'protection.ownership'):
        return
    enabled = get_setting('ownership_protection', '0') == '1'
    set_setting('ownership_protection', '0' if enabled else '1')
    add_log('security_log', 'ownership_protection', f"تم {'تعطيل' if enabled else 'تفعيل'} الإعداد")
    await ownership(c)


@router.callback_query(F.data == 'media_protection')
async def media(c):
    if await guard(c, 'protection.media_scan'):
        await show(c, '🖼️ فحص الوسائط\n\nالأرشفة متاحة. التحليل الآلي للمحتوى يحتاج محرك تحليل محتوى منفصل.', back('protection'))


@router.callback_query(F.data == 'security_log')
async def security(c):
    if not await guard(c, 'protection.log'):
        return
    rows = get_logs('security_log')
    await show(c, '📋 سجل الحماية\n\n' + ('لا توجد عمليات.' if not rows else '\n'.join(f"{r['created_at']} — {r['description']}" for r in rows)), back('protection'))


@router.callback_query(F.data == 'stats')
async def stats(c):
    if not await guard(c, 'stats'):
        return
    rows = list_private_chats()
    keys = ['message_count','photo_count','video_count','sticker_count','gif_count','link_count','audio_count','file_count']
    totals = {k: sum(r[k] or 0 for r in rows) for k in keys}
    await show(c, f"📊 الإحصائيات\n\n👥 الأشخاص: {len(rows)}\n💬 الرسائل: {totals['message_count']}\n🖼 الصور: {totals['photo_count']}\n🎥 الفيديوهات: {totals['video_count']}\n🃏 الملصقات: {totals['sticker_count']}\n🎞 GIF: {totals['gif_count']}\n🔗 الروابط: {totals['link_count']}\n🎙 الصوتيات: {totals['audio_count']}\n📎 الملفات: {totals['file_count']}", back('main_menu'))


@router.callback_query(F.data == 'search_messages')
async def search(c):
    if await guard(c, 'private.search'):
        await show(c, '🔎 البحث بالنص\n\nاختر المحادثة أولًا ثم تصفح السجل.', back('storage'))


@router.callback_query(F.data == 'rules')
async def rules(c):
    if await guard(c, 'automation.rules'):
        await show(c, '🧠 القواعد والأتمتة\n\nالوحدة جاهزة لإضافة قواعد مخصصة لاحقًا.', back('automation'))


@router.callback_query(F.data.startswith('operation_log'))
async def oplog(c):
    if not await guard(c, 'log.operations'):
        return
    parts = c.data.split(':')
    page = max(0, int(parts[1]) if len(parts) > 1 else 0)
    per_page = 8
    rows = get_logs('operation_log', limit=(page + 1) * per_page)
    # get_logs is newest-first, so render the requested page without adding a new DB query API.
    page_rows = rows[page * per_page:(page + 1) * per_page]
    if not page_rows:
        await show(c, '📋 سجل العمليات\n\nلا توجد عمليات.', InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🧹 تصفية سجل العمليات', callback_data='clear_operation_log')],[InlineKeyboardButton(text='🔙 الأتمتة', callback_data='automation')]]))
        return
    lines = ['📋 سجل العمليات', f'صفحة {page+1}', '']
    for r in page_rows:
        desc = str(r['description'] or '')
        if len(desc) > 180:
            desc = desc[:180] + '…'
        lines.append(f"🕐 {r['created_at']}\n⚙️ {r['event_type']}\n{desc}")
    nav=[]
    if page>0: nav.append(InlineKeyboardButton(text='⬅️ السابق', callback_data=f'operation_log:{page-1}'))
    if len(rows) > (page+1)*per_page: nav.append(InlineKeyboardButton(text='التالي ➡️', callback_data=f'operation_log:{page+1}'))
    rows_kb=[nav] if nav else []
    rows_kb.append([InlineKeyboardButton(text='🧹 تصفية سجل العمليات', callback_data='clear_operation_log')])
    rows_kb.append([InlineKeyboardButton(text='🔙 الأتمتة', callback_data='automation')])
    await show(c, '\n\n'.join(lines)[:3900], InlineKeyboardMarkup(inline_keyboard=rows_kb))


@router.callback_query(F.data == 'clear_operation_log')
async def clear_operation_log_cb(c):
    if not await guard(c):
        return
    clear_logs('operation_log')
    await show(c, '🧹 تم تصفية سجل العمليات بالكامل.', automation_menu())


# AI management
@router.callback_query(F.data == 'ai_settings')
async def ai_settings(c):
    if not await guard(c, 'ai.settings', owner_only=True):
        return
    enabled = get_setting('gemini_enabled', '1') != '0'
    trigger = get_setting('ai_trigger', '') or ''
    text = f"🤖 الذكاء الاصطناعي\n\nالحالة: {'🟢 يعمل' if enabled else '🔴 مغلق'}\nالاسم الإضافي: {trigger or 'غير موجود'}\n\nيعمل عند كتابة سبيشل + السؤال، أو الاسم الإضافي + السؤال."
    await show(c, text, ai_menu(enabled, trigger))


@router.callback_query(F.data == 'ai_toggle')
async def ai_toggle(c):
    if not await guard(c, 'ai.toggle', owner_only=True):
        return
    enabled = get_setting('gemini_enabled', '1') != '0'
    set_setting('gemini_enabled', '0' if enabled else '1')
    await ai_settings(c)


@router.callback_query(F.data == 'ai_set_trigger')
async def ai_set_trigger(c):
    if not await guard(c, 'ai.trigger', owner_only=True):
        return
    pending[user_id(c)] = {'action': 'ai_trigger_set'}
    await show(c, '✏️ اكتب الاسم الجديد للذكاء الاصطناعي\n\nمثال: حاتم', back('ai_settings'))


@router.callback_query(F.data == 'ai_clear_trigger')
async def ai_clear_trigger(c):
    if not await guard(c, 'ai.trigger', owner_only=True):
        return
    set_setting('ai_trigger', '')
    await ai_settings(c)


@router.callback_query(F.data == 'ai_logs')
async def ai_logs(c):
    if not await guard(c, 'ai.logs', owner_only=True):
        return
    rows = list_ai_logs(30)
    if not rows:
        await show(c, '📜 لا يوجد سجل أسئلة وأجوبة حتى الآن.', back('ai_settings'))
        return
    parts = ['📜 سجل الذكاء الاصطناعي', '']
    for r in rows:
        name = r['display_name'] or 'مستخدم'
        username = f"@{r['username']}" if r['username'] else 'بدون يوزر'
        parts.append(f"👤 {name} | {username} | ID: {r['user_id'] or '-'}\n📍 {r['source']} | chat: {r['chat_id'] or '-'}\n❓ {r['prompt']}\n🤖 {r['answer'][:500]}\n🕐 {r['created_at']}\n")
    await show(c, '\n'.join(parts)[:3900], back('ai_settings'))


# Developer/access management
@router.callback_query(F.data == 'access')
async def access(c):
    if await guard(c, owner_only=True):
        await show(c, '👑 إدارة المستخدمين المسموحين', access_menu())


@router.callback_query(F.data == 'access_add')
async def access_add(c):
    if await guard(c, owner_only=True):
        pending[user_id(c)] = {'action': 'access_add'}
        await show(c, '➕ أرسل ID الشخص الذي تريد السماح له.', back('access'))


@router.callback_query(F.data == 'access_list')
async def access_list(c):
    if not await guard(c, owner_only=True):
        return
    rows = get_allowed_users()
    buttons = [[InlineKeyboardButton(text=f"{'🟢' if r['status']=='active' else '🔴'} {r['display_name'] or r['user_id']}", callback_data=f'access_user:{r["user_id"]}')] for r in rows[:50]]
    buttons.append([InlineKeyboardButton(text='🔙 رجوع', callback_data='access')])
    await show(c, '👥 المستخدمون المسموحون\n\nاختر مستخدمًا:', InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == 'blocked_list')
async def blocked_list(c):
    if not await guard(c, owner_only=True):
        return
    rows = list_banned_users(100)
    if not rows:
        await show(c, '🚫 لا يوجد أشخاص محظورون حاليًا.', back('access'))
        return
    lines = ['🚫 المحظورون', '']
    for r in rows:
        username = f"@{r['username']}" if r['username'] else 'بدون يوزر'
        lines.append(f"👤 {r['display_name'] or 'مستخدم'} | {username}\n🆔 {r['user_id']}")
    await show(c, '\n\n'.join(lines)[:3900], back('access'))


@router.callback_query(F.data == 'access_unban')
async def access_unban(c):
    if await guard(c, owner_only=True):
        pending[user_id(c)] = {'action': 'access_unban'}
        await show(c, '🔓 أرسل ID المستخدم أو @username لإلغاء الحظر.', back('access'))


@router.callback_query(F.data == 'access_remove')
async def access_remove(c):
    if await guard(c, owner_only=True):
        pending[user_id(c)] = {'action': 'access_remove'}
        await show(c, '🗑️ أرسل ID المستخدم لإزالة صلاحية الوصول.', back('access'))


async def render_access_user(c, uid):
    r = get_allowed_user(uid)
    if not r:
        await c.answer('المستخدم غير موجود', show_alert=True)
        return
    await show(c, f"👤 {r['display_name'] or uid}\n🆔 {uid}\n📌 الحالة: {r['status']}\n⏱️ الصلاحية: {r['access_until'] or 'مدى الحياة'}", kb([[InlineKeyboardButton(text='🛠️ صلاحيات الميزات', callback_data=f'feature_permissions:{uid}:0')],[InlineKeyboardButton(text='⏸️ إيقاف مؤقت', callback_data=f'suspend:{uid}')],[InlineKeyboardButton(text='▶️ إعادة التفعيل', callback_data=f'resume:{uid}')],[InlineKeyboardButton(text='🚫 حظر', callback_data=f'ban:{uid}')],[InlineKeyboardButton(text='🗑️ إزالة', callback_data=f'remove:{uid}')],[InlineKeyboardButton(text='🔙 المستخدمون', callback_data='access_list')]]))


@router.callback_query(F.data.startswith('access_user:'))
async def access_user(c):
    if await guard(c, owner_only=True):
        await render_access_user(c, int(c.data.split(':')[1]))


@router.callback_query(F.data.startswith('feature_permissions:'))
async def feature_permissions(c):
    if not await guard(c, owner_only=True):
        return
    _, uid, page = c.data.split(':'); uid = int(uid); page = int(page)
    r = get_allowed_user(uid)
    if not r:
        await c.answer('المستخدم غير موجود', show_alert=True); return
    await show(c, f"🛠️ صلاحيات الميزات\n\n👤 {r['display_name'] or uid}", feature_permissions_menu(uid, get_feature_permissions(uid), page))


@router.callback_query(F.data.startswith('fp:'))
async def feature_toggle(c):
    if not await guard(c, owner_only=True):
        return
    _, uid, key, page = c.data.split(':', 3); uid = int(uid); page = int(page)
    cur = is_feature_enabled(uid, key); set_feature_permission(uid, key, not cur)
    await feature_permissions(c)


@router.callback_query(F.data.startswith('fpp:'))
async def feature_page(c):
    if await guard(c, owner_only=True):
        _, uid, page = c.data.split(':'); await show(c, f"🛠️ صلاحيات الميزات\n\n👤 {get_allowed_user(int(uid))['display_name'] or uid}", feature_permissions_menu(int(uid), get_feature_permissions(int(uid)), int(page)))


@router.callback_query(F.data.startswith('fpa:'))
async def feature_all(c):
    if not await guard(c, owner_only=True): return
    _, uid, flag = c.data.split(':'); uid = int(uid); set_all_feature_permissions(uid, flag == '1'); await feature_permissions(c)


@router.callback_query(F.data.startswith('suspend:'))
async def suspend(c):
    if await guard(c, owner_only=True):
        uid = int(c.data.split(':')[1]); pending[user_id(c)] = {'action': 'suspend_target', 'target': uid}; await show(c, '⏸️ اختر مدة الإيقاف:', durations_menu('suspend_duration'))


@router.callback_query(F.data.startswith('suspend_duration:'))
async def suspend_duration(c):
    if not await guard(c, owner_only=True): return
    state = pending.get(user_id(c), {}); uid = state.get('target'); val = c.data.split(':')[1]
    until = None if val == 'life' else (datetime.now(timezone.utc) + timedelta(days=int(val))).isoformat()
    update_allowed_status(uid, 'suspended', until); pending.pop(user_id(c), None); await render_access_user(c, uid)


@router.callback_query(F.data.startswith('resume:'))
async def resume(c):
    if await guard(c, owner_only=True): update_allowed_status(int(c.data.split(':')[1]), 'active', None); await access_list(c)


@router.callback_query(F.data.startswith('ban:'))
async def ban(c):
    if await guard(c, owner_only=True): update_allowed_status(int(c.data.split(':')[1]), 'banned', None); await access_list(c)


@router.callback_query(F.data.startswith('remove:'))
async def remove(c):
    if await guard(c, owner_only=True): remove_allowed_user(int(c.data.split(':')[1])); await access_list(c)


@router.callback_query(F.data == 'settings')
async def settings(c):
    if await guard(c, 'settings'):
        await show(c, '⚙️ الإعدادات العامة', settings_menu())


@router.callback_query(F.data == 'notification_settings')
async def notif(c):
    if await guard(c, 'notifications.settings'):
        await show(c, '🔔 إعدادات التنبيهات\n\nتم تفعيل تنبيهات التعديل والمستخدمين الجدد افتراضيًا.', back('settings'))


@router.callback_query(F.data == 'backup_settings')
async def backup_settings(c):
    if await guard(c, 'settings.backup'):
        await show(c, '💾 إعدادات النسخ الاحتياطي\n\nالنسخ الاحتياطي الكامل يحفظ قاعدة البيانات والسجل والوسائط.', back('settings'))


@router.callback_query(F.data == 'general_settings')
async def general_settings(c):
    if await guard(c, 'settings.general'):
        await show(c, '⚙️ إعدادات عامة\n\nSpecial يحفظ البيانات محليًا داخل المشروع.', back('settings'))
