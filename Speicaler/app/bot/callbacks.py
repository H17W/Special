from datetime import datetime, timezone, timedelta
from pathlib import Path
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile

from app.core.config import ADMIN_ID
from app.core.database import *
from app.core.permissions import FEATURES
from app.core.exporter import create_full_backup, create_chat_backup
from app.user.moderation import muted_users
from app.user.client import client as user_client, import_all_private_history, refresh_special, sync_all_private_users, manager
from .handlers import waiting_for_mute, waiting_for_unmute, pending, _send_access_request, audio_pending
from .keyboards import *

router = Router()

SECTION_KEYS = {"automation":"automation.monitor","private":"private.people","storage":"storage.backup","important":"important.add","broadcast":"broadcast.create","protection":"protection.media_scan","stats":"stats.people","settings":"settings.general"}
ACTION_KEYS = {
    "mute_user":"automation.mute","unmute_user":"automation.unmute","runtime_refresh":"automation.monitor","muted_list":"automation.muted_list","bot_access_log":"automation.monitor","mimic_settings":"automation.monitor","mimic_toggle":"automation.monitor","mimic_save_original":"automation.monitor","mimic_restore":"automation.monitor","rules":"automation.rules","operation_log":"log.operations",
    "private_people":"private.people","sync_private_users":"private.people","import_messages":"private.import","private_search":"private.people","search_messages":"private.search","stats":"stats.people",
    "backup":"storage.backup","backup_choose":"storage.backup","important_add":"important.add","important_list":"important.list",
    "broadcast_send":"broadcast.create","broadcast_confirm_send":"broadcast.send","broadcast_exclude":"broadcast.exclude","broadcast_exclusions":"broadcast.exclusions","broadcast_log":"broadcast.log","broadcast_scheduled":"broadcast.schedule",
    "ownership_protection":"protection.ownership","ownership_toggle":"protection.ownership","media_protection":"protection.media_scan","security_log":"protection.log","notification_settings":"notifications.settings","backup_settings":"settings.backup","general_settings":"settings.general",
    "ai_settings":"ai.settings","ai_toggle":"ai.toggle","ai_logs":"ai.logs","ai_set_trigger":"ai.trigger","ai_clear_trigger":"ai.trigger",
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
    # Inline keyboards injected into groups/channels by the owner's "الكيبورد" command are session-bound.
    try:
        session=get_keyboard_session(getattr(c.message.chat,'id',0),getattr(c.message,'message_id',0)) if c.message else None
        if session and int(session['owner_id']) != int(uid):
            strikes=record_rate_event(uid,'keyboard_unauthorized',300)
            if strikes>=3:
                set_bot_restriction(uid,(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),'keyboard_unauthorized',strikes)
                await c.answer('🚫 تم تقييدك 5 دقائق بسبب تكرار الضغط على لوحة غير مصرح لك باستخدامها.',show_alert=True)
            else:
                await c.answer('⛔ هذه لوحة خاصة بصاحب الطلب.',show_alert=True)
            return False
    except Exception:
        pass
    try:
        callback_hits=record_rate_event(uid,"callbacks",10)
        if callback_hits>30:
            set_bot_restriction(uid,(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),"callback_rate_limit",callback_hits)
            await c.answer('🚫 تم تقييد التفاعل 5 دقائق بسبب كثرة الطلبات.',show_alert=True)
            return False
    except Exception:
        pass
    if get_setting("bot_paused", "0") == "1":
        await c.answer('⏸️ البوت موقوف مؤقتًا. اكتب تفعيل داخل البوت لإعادته.', show_alert=True)
        return False
    if owner_only:
        if not is_admin(uid):
            await c.answer('⛔ هذه اللوحة للمالك فقط.', show_alert=True)
            return False
        return True
    if not is_admin(uid):
        r = get_allowed_user(uid)
        if not r or r['status'] != 'active':
            await c.answer('⛔ لا تملك صلاحية استخدام Special.', show_alert=True)
            return False
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
    await show(c, '🧠 أهلاً بك في Special\n\nلوحة التحكم الرئيسية:', main_menu(None) if is_admin(uid) else main_menu(uid, get_feature_permissions(uid), logged_in=manager.status(uid)))


@router.callback_query(F.data == 'automation')
async def automation(c):
    if await guard(c, 'automation'):
        await show(c, f'🧠 User Automation\n\n🔇 المكتومون: {len(muted_users())}', automation_menu(is_admin(user_id(c))))


@router.callback_query(F.data.startswith('bot_access_log'))
async def bot_access_history(c):
    if not await guard(c, 'automation.monitor', owner_only=True):
        return
    parts = c.data.split(':')
    page = int(parts[1]) if len(parts) > 1 else 0
    rows = list_bot_access_logs(20, page * 20)
    total = count_bot_access_logs()
    if not rows:
        await show(c, '👀 لا يوجد أشخاص دخلوا البوت حتى الآن.', back('automation'))
        return
    lines = ['👀 سجل دخول البوت', f'صفحة {page+1} — الإجمالي {total}', '']
    for r in rows:
        status = '✅ مسموح' if r['status'] == 'allowed' else '⛔ مرفوض'
        username = f"@{r['username']}" if r['username'] else 'بدون يوزر'
        lines.append(f"{status} | {r['display_name'] or 'مستخدم'} | {username} | ID: {r['user_id']}\n🕐 {r['created_at']}")
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='⬅️ الأحدث', callback_data=f'bot_access_log:{page-1}'))
    if (page + 1) * 20 < total:
        nav.append(InlineKeyboardButton(text='الأقدم ➡️', callback_data=f'bot_access_log:{page+1}'))
    rows_kb = [nav] if nav else []
    rows_kb.append([InlineKeyboardButton(text='🔙 الأتمتة', callback_data='automation')])
    await show(c, '\n\n'.join(lines)[:3900], InlineKeyboardMarkup(inline_keyboard=rows_kb))


@router.callback_query(F.data == 'mimic_settings')
async def mimic_settings(c):
    if not await guard(c, 'automation.monitor'):
        return
    settings = {k: get_setting(k, '1') for k in ['mimic_enabled','mimic_name','mimic_photo','mimic_bio','mimic_username','mimic_location']}
    text = (
        '👤 إعدادات التقليد\n\n'
        f"التقليد: {'🟢 يعمل' if settings['mimic_enabled']=='1' else '🔴 متوقف'}\n"
        f"الاسم: {'🟢' if settings['mimic_name']=='1' else '🔴'}\n"
        f"الصورة: {'🟢' if settings['mimic_photo']=='1' else '🔴'}\n"
        f"البايو: {'🟢' if settings['mimic_bio']=='1' else '🔴'}\n"
        f"يوزر مشابه: {'🟢' if settings['mimic_username']=='1' else '🔴'}\n"
        f"الموقع: {'🟢' if settings['mimic_location']=='1' else '🔴'}\n\n"
        'ملاحظة: الموقع الشخصي لا يملك له Telethon UpdateProfile حاليًا، لذلك يبقى الخيار محفوظًا لكن لن يغير موقع الحساب تلقائيًا.'
    )
    await show(c, text, mimic_menu(settings))


@router.callback_query(F.data == 'mimic_toggle')
async def mimic_toggle(c):
    if not await guard(c, 'automation.monitor'):
        return
    cur = get_setting('mimic_enabled', '1') == '1'
    set_setting('mimic_enabled', '0' if cur else '1')
    await mimic_settings(c)


@router.callback_query(F.data.startswith('mimic_toggle:'))
async def mimic_toggle_field(c):
    if not await guard(c, 'automation.monitor'):
        return
    keymap = {'name':'mimic_name','photo':'mimic_photo','bio':'mimic_bio','username':'mimic_username','location':'mimic_location'}
    key = keymap.get(c.data.split(':',1)[1])
    if not key:
        await c.answer('إعداد غير معروف', show_alert=True); return
    cur = get_setting(key, '1') == '1'
    set_setting(key, '0' if cur else '1')
    await mimic_settings(c)


@router.callback_query(F.data == 'mimic_save_original')
async def mimic_save_original(c):
    if not await guard(c, 'automation.monitor'):
        return
    try:
        from app.user.client import _backup_current_profile
        await _backup_current_profile()
        await c.answer('✅ تم حفظ بيانات حسابك الأصلية', show_alert=True)
    except Exception as exc:
        await c.answer(f'❌ فشل الحفظ: {type(exc).__name__}', show_alert=True)


@router.callback_query(F.data == 'mimic_restore')
async def mimic_restore(c):
    if not await guard(c, 'automation.monitor'):
        return
    try:
        from app.user.client import restore_profile
        ok = await restore_profile()
        await c.answer('✅ تمت الاستعادة' if ok else 'ℹ️ لا توجد نسخة أصلية محفوظة', show_alert=True)
        await mimic_settings(c)
    except Exception as exc:
        await c.answer(f'❌ فشل الاستعادة: {type(exc).__name__}', show_alert=True)


@router.callback_query(F.data == 'delete_chat')
async def delete_chat(c):
    if not await guard(c,'automation.monitor'): return
    pending[user_id(c)]={'action':'delete_choose_chat'}
    rows=list_private_chats()[:40]
    buttons=[[InlineKeyboardButton(text=f'👤 {r["display_name"] or r["user_id"]}',callback_data=f'delete_target:{r["user_id"]}')] for r in rows]
    buttons.append([InlineKeyboardButton(text='🆔 إدخال ID / @username',callback_data='delete_target_manual')])
    buttons.append([InlineKeyboardButton(text='🔙 الأتمتة',callback_data='automation')])
    await show(c,'🧹 مسح المحادثة\n\nاختر المحادثة المستهدفة ثم وجّه الرسالة الأولى للبوت وبعدها الرسالة الثانية. البوت سيحذف النطاق فورًا.',InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith('delete_target:'))
async def delete_target(c):
    if not await guard(c,'automation.monitor'): return
    target=int(c.data.split(':')[1]); pending[user_id(c)]={'action':'delete_start_forward','chat_id':target}
    await show(c,f'🎯 تم تحديد المحادثة: {target}\n\nالآن وجّه أول رسالة إلى البوت — هذه ستكون بداية الحذف. ثم وجّه الرسالة الثانية — هذه ستكون نهاية الحذف.',back('automation'))

@router.callback_query(F.data == 'delete_target_manual')
async def delete_target_manual(c):
    if not await guard(c,'automation.monitor'): return
    pending[user_id(c)]={'action':'delete_choose_chat_manual'}
    await show(c,'🆔 أرسل ID أو @username للمحادثة المستهدفة.',back('automation'))

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
        msg = '🩺 فحص Special\n\n🟢 قاعدة البيانات: تعمل\n'
        msg += f"🟢 Telegram: {'متصل' if manager.status(user_id(c)) else 'غير متصل'}\n"
        msg += '🖼️ تم تحديث بيانات وصورة التقليد الحالي.' if result.get('mimic_refreshed') else '📥 تمت مزامنة وفحص بيانات الخاص.'
        await show(c, msg, automation_menu(is_admin(user_id(c))))
    except Exception as exc:
        await c.message.answer(f'❌ تعذر فحص النظام: {type(exc).__name__}')
        await c.answer()

@router.callback_query(F.data == 'mute_user')
async def mute_cb(c):
    if await guard(c, 'automation.mute'):
        waiting_for_mute.add(user_id(c))
        await show(c, '🔇 كتم مستخدم\n\nأرسل Telegram ID للمستخدم.', back('automation'))


@router.callback_query(F.data == 'unmute_user')
async def unmute_cb(c):
    if await guard(c, 'automation.unmute'):
        waiting_for_unmute.add(user_id(c))
        await show(c, '🔊 إلغاء كتم\n\nأرسل Telegram ID للمستخدم.', back('automation'))


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
    await c.message.edit_text('📥 جاري استيراد الرسائل القديمة من الخاص فقط...\n\nلا يتم استيراد البوتات أو القروبات أو القنوات.')
    try:
        result = await import_all_private_history()
        await c.message.answer('✅ تم استيراد الرسائل بنجاح\n\n' f"👥 المحادثات: {result['chats']}\n💬 الرسائل الجديدة: {result['messages']}\n⏭️ الرسائل الموجودة مسبقًا: {result['skipped']}", reply_markup=private_menu())
    except Exception as exc:
        await c.message.answer(f'❌ تعذر استيراد الرسائل: {type(exc).__name__}', reply_markup=private_menu())
    await c.answer()


@router.callback_query(F.data == 'private_search')
async def private_search(c):
    if await guard(c, 'private.people'):
        pending[user_id(c)] = {'action': 'private_search'}
        await show(c, '🔎 أرسل الاسم أو @username أو Telegram ID للبحث في الأشخاص الحقيقيين في الخاص.', back('private'))


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
    lines = ['📖 سجل المحادثة', '']
    for r in rows:
        direction = '👤' if r['direction'] == 'incoming' else '➡️'
        lines.append(f"[{r['message_date'] or ''}] {direction} {r['text'] or '['+(r['media_type'] or 'وسائط')+']'}")
    nav = []
    if int(offset) > 0:
        nav.append(InlineKeyboardButton(text='⬅️ الأقدم', callback_data=f'browse:{uid}:{max(0,int(offset)-10)}'))
    if len(rows) == 10:
        nav.append(InlineKeyboardButton(text='الأحدث ➡️', callback_data=f'browse:{uid}:{int(offset)+10}'))
    rows_kb = [nav] if nav else []
    rows_kb.append([InlineKeyboardButton(text='🔙 المحادثة', callback_data=f'chat:{uid}')])
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
        path = create_full_backup()
        await c.message.answer_document(FSInputFile(path), caption='💾 تم إنشاء النسخة الاحتياطية الكاملة لـ Special')
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
            await user_client.send_message(int(row['user_id']), text)
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
        await show(c, '🔎 البحث بالنص\n\nاختر المحادثة أولًا ثم تصفح السجل.', back('private'))


@router.callback_query(F.data == 'rules')
async def rules(c):
    if await guard(c, 'automation.rules'):
        await show(c, '🧠 القواعد والأتمتة\n\nالوحدة جاهزة لإضافة قواعد مخصصة لاحقًا.', back('automation'))


@router.callback_query(F.data == 'operation_log')
async def oplog(c):
    if not await guard(c, 'log.operations'):
        return
    rows=get_logs('operation_log',50)
    text='📋 سجل العمليات\n\n'+('لا توجد عمليات.' if not rows else '\n'.join(f"{r['created_at']} — {r['description']}" for r in rows))
    await show(c,text,back('automation'))


# Music + developer-only panel
@router.callback_query(F.data == 'audio_edit')
async def audio_edit(c):
    uid=user_id(c); data=audio_pending.get(uid)
    if not data: await c.answer('❌ انتهت جلسة الملف الصوتي.',show_alert=True); return
    pending[uid]={'action':'audio_edit'}
    await c.message.answer('✏️ أرسل البيانات بهذا الشكل:\nاسم المقطع | اسم الفنان\n\nاسم الفنان اختياري.')
    await c.answer()

@router.callback_query(F.data == 'audio_voice')
async def audio_voice(c):
    uid=user_id(c); data=audio_pending.get(uid)
    if not data or not Path(data['path']).exists(): await c.answer('❌ انتهت جلسة الملف الصوتي.',show_alert=True); return
    import subprocess, tempfile, os
    out=os.path.join(data['dir'],'voice.ogg')
    try:
        subprocess.run(['ffmpeg','-y','-i',data['path'],'-c:a','libopus','-b:a','48k','-vn',out],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120)
        await c.bot.send_voice(uid,FSInputFile(out),caption=f"🎙️ {data.get('name') or 'Voice Note'}")
        await c.message.edit_text('✅ تم تحويل المقطع إلى رسالة صوتية وإرسالها.')
    except Exception as exc:
        await c.message.edit_text(f'❌ تعذر تحويل الصوت: {type(exc).__name__}')
    finally:
        try:
            import shutil; shutil.rmtree(data['dir'],ignore_errors=True)
        except Exception: pass
        audio_pending.pop(uid,None); pending.pop(uid,None); await c.answer()

@router.callback_query(F.data == 'music')
async def music(c):
    if await guard(c):
        await show(c, '🎵 Music Studio\n\nابحث عن أصوات وملفات صوتية متاحة للتنزيل من المصادر المسموح بها ثم أرسلها مباشرة إلى خاص البوت.', music_menu())

@router.callback_query(F.data == 'music_search')
async def music_search(c):
    if await guard(c, 'music.search'):
        pending[user_id(c)] = {'action': 'music_search'}
        await show(c, '🔎 اكتب اسم الأغنية أو الفنان أو كلمات البحث.\n\nمثال:\nMozart Eine kleine Nachtmusik', back('music'))

@router.callback_query(F.data == 'music_results')
async def music_results(c):
    if await guard(c, 'music.search'):
        await show(c, '📚 النتائج تحفظ مؤقتًا داخل جلسة المحادثة فقط.', back('music'))

@router.callback_query(F.data.startswith('music_get:'))
async def music_get(c):
    if not await guard(c, 'music.download'): return
    identifier = c.data.split(':',1)[1]
    uid = user_id(c)
    await c.answer('⏳ جاري تجهيز الملف الصوتي...', show_alert=False)
    from app.core.music import download_music
    from app.user.client import account_root
    import tempfile, os
    tmp = Path(tempfile.mkdtemp(prefix='special_music_'))
    try:
        path = await download_music(identifier, tmp)
        if not path:
            await show(c, '❌ هذا العنصر لا يحتوي على ملف صوتي قابل للتنزيل.', back('music'))
            return
        from aiogram.types import ReplyParameters
        reply_target = music_reply_targets.get(uid, {}).get(identifier)
        kwargs = {'caption': f'🎧 تم جلب الملف الصوتي\n🆔 المصدر: {identifier}'}
        if reply_target:
            kwargs['reply_parameters'] = ReplyParameters(message_id=int(reply_target))
        await c.bot.send_audio(uid, FSInputFile(path), **kwargs)
        music_reply_targets.get(uid, {}).pop(identifier, None)
        await show(c, '✅ تم إرسال الملف الصوتي كرد على رسالة البحث.\n\n🧹 تم حذف النسخة المؤقتة من السيرفر بعد الإرسال.', back('music'))
    except Exception as exc:
        await show(c, f'❌ تعذر جلب الملف: {type(exc).__name__}', back('music'))
    finally:
        try:
            for f in tmp.iterdir(): f.unlink(missing_ok=True)
            tmp.rmdir()
        except Exception: pass

@router.callback_query(F.data == 'developer_panel')
async def developer_panel(c):
    if await guard(c, owner_only=True):
        await show(c, '👑 لوحة المطور\n\nهذه المنطقة خاصة بالمطور فقط.\nكل ما يتعلق بإدارة المستخدمين والصلاحيات والإحصائيات والسجلات والحسابات يظهر هنا فقط.', developer_menu())

@router.callback_query(F.data == 'dev_permission_search')
async def dev_permission_search(c):
    if not await guard(c, owner_only=True): return
    pending[user_id(c)] = {'action':'dev_permission_search'}
    await show(c, '🔍 أرسل Telegram ID للمستخدم الذي تريد فحص صلاحياته.', back('developer_panel'))

@router.callback_query(F.data == 'dev_stats')
async def dev_stats(c):
    if not await guard(c, owner_only=True): return
    rows = get_allowed_users()
    active = sum(1 for r in rows if r['status']=='active')
    online = sum(1 for r in rows if manager.status(r['user_id']))
    await show(c, f'📊 إحصائيات البوت\n\n👥 المسموح لهم: {len(rows)}\n🟢 النشطون: {active}\n📡 الحسابات المتصلة: {online}\n👀 سجلات الدخول: {count_bot_access_logs()}\n\n👑 هذه الصفحة خاصة بالمطور.', back('developer_panel'))

@router.callback_query(F.data == 'dev_security')
async def dev_security(c):
    if await guard(c, owner_only=True):
        await show(c, '🔐 مركز الأمان للمطور\n\n• أكواد Telegram لا تُحفظ\n• كلمات مرور 2FA لا تُحفظ\n• جلسات الحسابات معزولة لكل مستخدم\n• ملفات الوسائط المؤقتة تُحذف بعد إرسالها إلى خاص البوت', back('developer_panel'))

@router.callback_query(F.data == 'dev_accounts')
async def dev_accounts(c):
    if not await guard(c, owner_only=True): return
    rows=[]
    for r in get_allowed_users():
        rows.append(f"{'🟢' if manager.status(r['user_id']) else '🔴'} {r['display_name'] or r['user_id']} — {r['user_id']}")
    await show(c, '🔄 إدارة حسابات المستخدمين\n\n' + ('لا توجد حسابات مسموحة.' if not rows else '\n'.join(rows)), back('developer_panel'))

# AI management
@router.callback_query(F.data == 'ai_settings')
async def ai_settings(c):
    if not await guard(c, 'ai.settings'):
        return
    enabled = get_setting('gemini_enabled', '1') != '0'
    trigger = get_setting('ai_trigger', '') or ''
    text = f"🤖 الذكاء الاصطناعي\n\nالحالة: {'🟢 يعمل' if enabled else '🔴 مغلق'}\nالاسم الإضافي: {trigger or 'غير موجود'}\n\nيعمل عند كتابة سبيشل + السؤال، أو الاسم الإضافي + السؤال."
    await show(c, text, ai_menu(enabled, trigger))


@router.callback_query(F.data == 'ai_toggle')
async def ai_toggle(c):
    if not await guard(c, 'ai.toggle'):
        return
    enabled = get_setting('gemini_enabled', '1') != '0'
    set_setting('gemini_enabled', '0' if enabled else '1')
    await ai_settings(c)


@router.callback_query(F.data == 'ai_set_trigger')
async def ai_set_trigger(c):
    if not await guard(c, 'ai.trigger'):
        return
    pending[user_id(c)] = {'action': 'ai_trigger_set'}
    await show(c, '✏️ اكتب الاسم الجديد للذكاء الاصطناعي\n\nمثال: حاتم', back('ai_settings'))


@router.callback_query(F.data == 'ai_clear_trigger')
async def ai_clear_trigger(c):
    if not await guard(c, 'ai.trigger'):
        return
    set_setting('ai_trigger', '')
    await ai_settings(c)


@router.callback_query(F.data == 'ai_logs')
async def ai_logs(c):
    if not await guard(c, 'ai.logs'):
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


# Access request workflow
@router.callback_query(F.data == 'request_access')
async def request_access(c):
    uid=user_id(c)
    if is_admin(uid) or (get_allowed_user(uid) and get_allowed_user(uid)['status']=='active'):
        await c.answer('أنت مصرح لك بالفعل',show_alert=True); return
    row=get_bot_access_request(uid)
    if row and row['status']=='pending':
        await c.answer('تم إرسال طلبك بالفعل وهو قيد المراجعة.',show_alert=True); return
    upsert_bot_access_request(uid,c.from_user.full_name or 'مستخدم',c.from_user.username)
    try: await c.message.edit_text('✅ تم إرسال طلبك للمطور بنجاح')
    except Exception: await c.message.answer('✅ تم إرسال طلبك للمطور بنجاح')
    await c.answer()
    if ADMIN_ID:
        name=c.from_user.full_name or 'مستخدم'; username=c.from_user.username
        url=f'https://t.me/{username}' if username else f'tg://user?id={uid}'
        markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='✅ قبول دائم',callback_data=f'req_accept:{uid}')],
            [InlineKeyboardButton(text='⏳ قبول مؤقت',callback_data=f'req_duration:{uid}')],
            [InlineKeyboardButton(text='❌ رفض',callback_data=f'req_reject:{uid}')],
        ])
        await c.bot.send_message(int(ADMIN_ID),f'📨 طلب استخدام Special\n\n👤 الاسم: {name}\n🆔 ID: {uid}\n🔗 Username: {("@"+username) if username else "لا يوجد يوزر"}\n\nاختر الإجراء:',reply_markup=markup)

@router.callback_query(F.data.startswith('req_accept:'))
async def req_accept(c):
    if not await guard(c,owner_only=True): return
    uid=int(c.data.split(':')[1]); row=get_bot_access_request(uid)
    if not row or row['status']!='pending': await c.answer('الطلب منتهي أو تمت معالجته',show_alert=True); return
    add_allowed_user(uid,row['username'],row['display_name'],None); set_bot_access_request(uid,'approved','permanent',None,None)
    await c.message.edit_text(f'✅ تم قبول طلب استخدام Special\n\n🆔 ID: {uid}\n📌 السماح: دائم')
    try: await c.bot.send_message(uid,'✅ تم قبول طلبك لاستخدام Special')
    except Exception: pass
    await c.answer()

@router.callback_query(F.data.startswith('req_duration:'))
async def req_duration(c):
    if not await guard(c,owner_only=True): return
    uid=int(c.data.split(':')[1]); pending[user_id(c)]={'action':'request_duration_target','target':uid}
    await show(c,'⏳ اختر مدة السماح:',durations_menu('request_duration'))

@router.callback_query(F.data.startswith('request_duration:'))
async def request_duration(c):
    if not await guard(c,owner_only=True): return
    state=pending.get(user_id(c),{}); uid=state.get('target'); val=c.data.split(':')[1]
    if not uid: await c.answer('الطلب غير موجود',show_alert=True); return
    row=get_bot_access_request(uid)
    if not row or row['status']!='pending': await c.answer('الطلب منتهي',show_alert=True); return
    until=None if val=='life' else (datetime.now(timezone.utc)+timedelta(days=int(val))).isoformat()
    add_allowed_user(uid,row['username'],row['display_name'],until); set_bot_access_request(uid,'approved','temporary' if until else 'permanent',None,until); pending.pop(user_id(c),None)
    duration='مدى الحياة' if not until else f'{val} يوم'
    await c.message.edit_text(f'✅ تم قبول طلب استخدام Special\n\n🆔 ID: {uid}\n⏳ المدة: {duration}')
    try: await c.bot.send_message(uid,f'✅ تم قبول طلبك لاستخدام Special\n\n⏳ مدة السماح: {duration}')
    except Exception: pass
    await c.answer()

@router.callback_query(F.data.startswith('req_reject:'))
async def req_reject(c):
    if not await guard(c,owner_only=True): return
    uid=int(c.data.split(':')[1]); row=get_bot_access_request(uid)
    if not row or row['status']!='pending': await c.answer('الطلب منتهي',show_alert=True); return
    await show(c,'❌ اختر طريقة الرفض:',kb([[InlineKeyboardButton(text='❌ رفض بدون سبب',callback_data=f'req_reject_plain:{uid}')],[InlineKeyboardButton(text='📝 رفض مع سبب',callback_data=f'req_reject_reason:{uid}')],[InlineKeyboardButton(text='🔙 رجوع',callback_data='developer_panel')]]))

@router.callback_query(F.data.startswith('req_reject_plain:'))
async def req_reject_plain(c):
    if not await guard(c,owner_only=True): return
    uid=int(c.data.split(':')[1]); row=get_bot_access_request(uid)
    if not row or row['status']!='pending': await c.answer('الطلب منتهي',show_alert=True); return
    set_bot_access_request(uid,'denied','rejected',None,None)
    await c.message.edit_text(f'❌ تم رفض طلب استخدام Special\n\n🆔 ID: {uid}')
    try: await c.bot.send_message(uid,'❌ تم رفض طلبك لاستخدام Special')
    except Exception: pass
    await c.answer()

@router.callback_query(F.data.startswith('req_reject_reason:'))
async def req_reject_reason(c):
    if not await guard(c,owner_only=True): return
    uid=int(c.data.split(':')[1]); pending[user_id(c)]={'action':'access_reject_reason','target':uid}
    await show(c,'📝 أرسل سبب الرفض الآن. سيتم إرساله للمستخدم كما هو.',back('developer_panel'))

@router.callback_query(F.data == 'temp_invite')
async def temp_invite(c):
    if not await guard(c,owner_only=True): return
    pending[user_id(c)]={'action':'invite_duration'}
    await show(c,'🔗 اختر مدة رابط الدخول المؤقت:',durations_menu('invite_duration'))

@router.callback_query(F.data.startswith('invite_duration:'))
async def invite_duration(c):
    if not await guard(c,owner_only=True): return
    val=c.data.split(':')[1]; from secrets import token_urlsafe
    from app.core.database import create_invite_token
    bot_me=await c.bot.get_me(); token=token_urlsafe(18)
    until=(datetime.now(timezone.utc)+timedelta(days=int(val))).isoformat() if val!='life' else (datetime.now(timezone.utc)+timedelta(days=3650)).isoformat()
    create_invite_token(token,user_id(c),until); pending.pop(user_id(c),None)
    link=f'https://t.me/{bot_me.username}?start=invite_{token}'
    await show(c,f'🔗 رابط دخول مؤقت\n\n⏳ المدة: {"مدى الحياة" if val=="life" else val+" يوم"}\n\n{link}',back('developer_panel'))

@router.callback_query(F.data == 'access_requests')
async def access_requests(c):
    if not await guard(c,owner_only=True): return
    rows=list_pending_bot_access_requests()
    if not rows: await show(c,'📨 لا توجد طلبات استخدام معلقة.',back('developer_panel')); return
    buttons=[[InlineKeyboardButton(text=f'👤 {r["display_name"] or r["user_id"]} | {r["user_id"]}',callback_data=f'req_reject:{r["user_id"]}')] for r in rows[:30]]
    buttons.append([InlineKeyboardButton(text='🔙 المطور',callback_data='developer_panel')])
    await show(c,'📨 طلبات استخدام Special\n\nاختر طلبًا لمراجعته:',InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data == 'bot_restrict')
async def bot_restrict(c):
    if not await guard(c,owner_only=True): return
    pending[user_id(c)]={'action':'bot_restrict_target'}
    await show(c,'🚫 أرسل ID أو @username للمستخدم الذي تريد تقييد استخدامه لـ Special. يمكنك أيضًا الرد على رسالة المستخدم ثم كتابة الأمر النصي.',back('developer_panel'))

@router.callback_query(F.data == 'private_lock')
async def private_lock(c):
    if not await guard(c,owner_only=True): return
    current=get_setting('private_lock','0')=='1'; set_setting('private_lock','0' if current else '1')
    await show(c,('🔓 تم فتح الخاص للجميع.' if current else '🔒 تم قفل الخاص: رسائل غير المستثنين ستحذف تلقائيًا.'),developer_menu())

@router.callback_query(F.data == 'private_lock_add')
async def private_lock_add(c):
    if not await guard(c,owner_only=True): return
    pending[user_id(c)]={'action':'private_lock_add'}
    await show(c,'👤 أرسل ID أو @username للشخص المستثنى من قفل الخاص.',back('developer_panel'))

@router.callback_query(F.data == 'private_lock_remove')
async def private_lock_remove(c):
    if not await guard(c,owner_only=True): return
    pending[user_id(c)]={'action':'private_lock_remove'}
    await show(c,'🧹 أرسل ID أو @username للشخص الذي تريد إلغاء استثنائه.',back('developer_panel'))

@router.callback_query(F.data == 'profanity_toggle')
async def profanity_toggle(c):
    if not await guard(c,owner_only=True): return
    current=get_setting('profanity_filter','0')=='1'; set_setting('profanity_filter','0' if current else '1')
    await show(c,('🔓 تم فتح الشتم.' if current else '🛡️ تم قفل الشتم وتفعيل الحذف التلقائي للمخالفات.'),developer_menu())

@router.callback_query(F.data.startswith('access_time:'))
async def access_time(c):
    if not await guard(c,owner_only=True): return
    uid=int(c.data.split(':')[1]); r=get_allowed_user(uid)
    if not r: await c.answer('المستخدم غير موجود',show_alert=True); return
    until=r['access_until']
    if not until: text='⏳ الوقت المتبقي: ♾️ سماح دائم'
    else:
        try:
            left=datetime.fromisoformat(until)-datetime.now(timezone.utc); seconds=max(0,int(left.total_seconds()))
            days,rem=divmod(seconds,86400); hours,rem=divmod(rem,3600); mins,_=divmod(rem,60)
            text=f'⏳ الوقت المتبقي: {days} يوم {hours} ساعة {mins} دقيقة\n📅 ينتهي: {until}' if seconds>0 else '⏳ انتهت صلاحية المستخدم'
        except Exception: text=f'⏳ ينتهي: {until}'
    await c.answer(text,show_alert=True)

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
    await show(c, f"👤 {r['display_name'] or uid}\n🆔 {uid}\n📌 الحالة: {r['status']}\n⏱️ الصلاحية: {r['access_until'] or 'مدى الحياة'}", kb([[InlineKeyboardButton(text='🛠️ صلاحيات الميزات', callback_data=f'feature_permissions:{uid}:0')],[InlineKeyboardButton(text='⏳ الوقت المتبقي', callback_data=f'access_time:{uid}')],[InlineKeyboardButton(text='⏸️ إيقاف مؤقت', callback_data=f'suspend:{uid}')],[InlineKeyboardButton(text='▶️ إعادة التفعيل', callback_data=f'resume:{uid}')],[InlineKeyboardButton(text='🚫 حظر', callback_data=f'ban:{uid}')],[InlineKeyboardButton(text='🗑️ إزالة', callback_data=f'remove:{uid}')],[InlineKeyboardButton(text='🔙 المستخدمون', callback_data='access_list')]]))


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



@router.callback_query(F.data == 'account')
async def account(c):
    if not await guard(c):
        return
    uid = user_id(c)
    status = manager.status(uid)
    await show(c, f"👤 حسابي\n\n🆔 Bot ID: {uid}\n📡 الحالة: {'🟢 متصل' if status else '🔴 غير متصل'}\n\nهذا الحساب معزول عن بقية المستخدمين: إعداداته وملفاته ووسائطه وسجل الخاص منفصلة.", account_menu(status))


@router.callback_query(F.data == 'account_status')
async def account_status(c):
    if await guard(c):
        uid = user_id(c)
        status = manager.status(uid)
        await c.answer('🟢 الحساب متصل ويعمل' if status else '🔴 الحساب غير متصل — استخدم تسجيل حسابي', show_alert=True)


@router.callback_query(F.data == 'account_login')
async def account_login(c):
    if await guard(c):
        from .handlers import login_state
        login_state[user_id(c)] = {'action': 'phone'}
        await show(c, '🔐 تسجيل حساب Telegram\n\nأرسل رقم هاتف حسابك بصيغة دولية.\nبعدها سيرسل Telegram كود الدخول، وإذا كان الحساب محميًا بـ 2FA سيُطلب منك كلمة المرور مؤقتًا ولن يتم حفظها.', back('account'))


@router.callback_query(F.data == 'account_logout')
async def account_logout(c):
    if await guard(c):
        uid = user_id(c)
        if not manager.status(uid):
            await c.answer('ℹ️ ما فيه حساب متصل', show_alert=True); return
        await manager.logout(uid)
        await c.answer('🚪 تم تسجيل خروج حساب Telegram من Special', show_alert=True)
        await account(c)


@router.callback_query(F.data == 'account_switch')
async def account_switch(c):
    if await guard(c):
        await show(c, '🔄 إدارة الحساب\n\nجلسة Telegram الحالية مستقلة تمامًا عن بقية المستخدمين. من هنا تقدر تعيد تسجيل الحساب أو تسجيل الخروج ثم ربط حساب آخر بدون خلط سجل أو إعدادات الحساب السابق.', back('account'))


@router.callback_query(F.data == 'security_center')
async def security_center(c):
    if await guard(c):
        uid = user_id(c)
        logs = get_logs('security_log', 12)
        lines = [f'🔐 مركز الأمان\n\n📡 جلسة Telegram: {"🟢 متصلة" if manager.status(uid) else "🔴 غير متصلة"}', '🧩 بيانات الحساب معزولة عن المستخدمين الآخرين.', '🔑 أكواد Telegram وكلمة مرور 2FA لا تُحفظ في قاعدة البيانات.']
        if logs:
            lines.append('\nآخر أحداث الأمان:')
            lines.extend(f"• {r['event_type']} — {r['created_at']}" for r in logs[:8])
        await show(c, '\n'.join(lines), back('account'))

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
