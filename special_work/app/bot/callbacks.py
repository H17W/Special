from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from app.core.config import ADMIN_ID
from app.core.database import *
from app.core.permissions import FEATURES
from app.core.exporter import create_full_backup, create_chat_backup
from app.user.moderation import muted_users
from app.user.client import client as user_client
from .handlers import waiting_for_mute, waiting_for_unmute, pending
from .keyboards import *

router=Router()
SECTION_KEYS={
 "automation":"automation.monitor","private":"private.people","storage":"storage.backup","important":"important.add","broadcast":"broadcast.create","protection":"protection.media_scan","stats":"stats.people","settings":"settings.general",
}
ACTION_KEYS={
 "mute_user":"automation.mute","unmute_user":"automation.unmute","muted_list":"automation.muted_list","rules":"automation.rules","operation_log":"log.operations",
 "private_people":"private.people","search_messages":"private.search","stats":"stats.people","backup":"storage.backup","backup_choose":"storage.backup","important_add":"important.add","important_list":"important.list",
 "broadcast_send":"broadcast.create","broadcast_confirm_send":"broadcast.send","broadcast_exclude":"broadcast.exclude","broadcast_exclusions":"broadcast.exclusions","broadcast_log":"broadcast.log","broadcast_scheduled":"broadcast.schedule",
 "ownership_protection":"protection.ownership","ownership_toggle":"protection.ownership","media_protection":"protection.media_scan","security_log":"protection.log","notification_settings":"notifications.settings","backup_settings":"settings.backup","general_settings":"settings.general",
}

def is_admin(uid): return bool(ADMIN_ID and str(uid)==str(ADMIN_ID))
def user_id(c): return c.from_user.id if c.from_user else 0

def feature_allowed(uid,key):
    if is_admin(uid): return True
    r=get_allowed_user(uid)
    if not r or r['status']!='active': return False
    # A parent section is allowed when any child is enabled.
    if '.' not in key:
        return any(is_feature_enabled(uid,k) for k,_ in FEATURES if k.startswith(key+'.'))
    return is_feature_enabled(uid,key)

def key_for_callback(data):
    if data in SECTION_KEYS:return SECTION_KEYS[data]
    if data in ACTION_KEYS:return ACTION_KEYS[data]
    if data.startswith('chat:') or data.startswith('browse:'):return 'private.open_chat'
    if data.startswith('backup:'):return 'storage.backup'
    if data.startswith('feature_') or data.startswith('fp:') or data.startswith('fpp:') or data.startswith('fpa:'):return None
    if data.startswith('access') or data.startswith('suspend') or data.startswith('resume') or data.startswith('ban') or data.startswith('remove') or data.startswith('extend'):return None
    return None

async def guard(c,key=None,owner_only=False):
    uid=user_id(c)
    if owner_only:
        if not is_admin(uid): await c.answer('⛔ هذه اللوحة للمالك فقط.',show_alert=True); return False
        return True
    r=get_allowed_user(uid) if not is_admin(uid) else None
    if not is_admin(uid) and (not r or r['status']!='active'):
        await c.answer('⛔ لا تملك صلاحية استخدام Special.',show_alert=True); return False
    if key and not feature_allowed(uid,key):
        await c.answer('🚫 هذه الميزة ممنوعة عن حسابك من لوحة المطور.',show_alert=True); return False
    return True

async def show(c,text,markup):
    try: await c.message.edit_text(text,reply_markup=markup)
    except Exception: await c.message.answer(text,reply_markup=markup)
    await c.answer()

@router.callback_query()
async def permission_gate(c:CallbackQuery):
    # This handler runs only as a fallback for unknown callbacks; registered handlers below take precedence in aiogram.
    return

@router.callback_query(F.data=='main_menu')
async def main(c):
    if await guard(c): await show(c,'🧠 أهلاً بك في Special\n\nلوحة التحكم الرئيسية:',main_menu(user_id(c),get_feature_permissions(user_id(c))))

@router.callback_query(F.data=='automation')
async def automation(c):
    if await guard(c,'automation'): await show(c,f'🧠 User Automation\n\n🔇 المكتومون: {len(muted_users())}',automation_menu())
@router.callback_query(F.data=='mute_user')
async def mute_cb(c):
    if await guard(c,'automation.mute'):
        waiting_for_mute.add(user_id(c)); await show(c,'🔇 كتم مستخدم\n\nأرسل Telegram ID للمستخدم.',back('automation'))
@router.callback_query(F.data=='unmute_user')
async def unmute_cb(c):
    if await guard(c,'automation.unmute'):
        waiting_for_unmute.add(user_id(c)); await show(c,'🔊 إلغاء كتم\n\nأرسل Telegram ID للمستخدم.',back('automation'))
@router.callback_query(F.data=='muted_list')
async def muted(c):
    if not await guard(c,'automation.muted_list'):return
    rows=muted_users(); text='👥 المكتومون\n\n'+('لا يوجد مستخدمون مكتومون.' if not rows else '\n'.join(f"🔇 {r['display_name'] or 'مستخدم'} | ID: {r['user_id']}" for r in rows)); await show(c,text,back('automation'))

@router.callback_query(F.data=='private')
async def private(c):
    if await guard(c,'private'): await show(c,'📥 إدارة الخاص\n\nإدارة الأشخاص والمحادثات المحفوظة.',private_menu())
@router.callback_query(F.data=='private_people')
async def private_people(c):
    if not await guard(c,'private.people'):return
    rows=list_private_chats(); buttons=[[InlineKeyboardButton(text=f"👤 {r['display_name'] or r['user_id']}",callback_data=f"chat:{r['user_id']}")] for r in rows[:80]]; buttons.append([InlineKeyboardButton(text='🔙 رجوع',callback_data='private')]); await show(c,'👥 الأشخاص في الخاص\n\nاختر شخصًا:',InlineKeyboardMarkup(inline_keyboard=buttons))
@router.callback_query(F.data.startswith('chat:'))
async def chat(c):
    if not await guard(c,'private.open_chat'):return
    uid=int(c.data.split(':',1)[1]); r=get_private_chat(uid)
    if not r: await c.answer('المحادثة غير موجودة',show_alert=True);return
    text=f"👤 {r['display_name'] or 'مستخدم'}\n🆔 ID: {uid}\n🔗 Username: {('@'+r['username']) if r['username'] else 'لا يوجد يوزر'}\n\n💬 الرسائل: {r['message_count']}\n🖼 الصور: {r['photo_count']}\n🎥 الفيديوهات: {r['video_count']}\n🃏 الملصقات: {r['sticker_count']}\n🎞 المتحركات: {r['gif_count']}\n🔗 الروابط: {r['link_count']}"
    await show(c,text,kb([[InlineKeyboardButton(text='📖 تصفح السجل',callback_data=f'browse:{uid}:0')],[InlineKeyboardButton(text='💾 نسخ احتياطي',callback_data=f'backup:{uid}')],[InlineKeyboardButton(text='🔙 الأشخاص',callback_data='private_people')]]))
@router.callback_query(F.data.startswith('browse:'))
async def browse(c):
    if not await guard(c,'storage.browse'):return
    _,uid,offset=c.data.split(':'); rows=list_messages(int(uid),10,int(offset));
    if not rows: await show(c,'📖 لا توجد رسائل محفوظة.',back(f'chat:{uid}'));return
    lines=['📖 سجل المحادثة','']
    for r in rows: lines.append(f"[{r['message_date'] or ''}] {'👤' if r['direction']=='incoming' else '➡️'} {r['text'] or '['+(r['media_type'] or 'وسائط')+']'}{' ✏️' if r['edited_at'] else ''}{' 🗑️' if r['deleted_at'] else ''}")
    nav=[]
    if int(offset)>=10:nav.append(InlineKeyboardButton(text='⬅️ السابق',callback_data=f'browse:{uid}:{max(0,int(offset)-10)}'))
    nav.append(InlineKeyboardButton(text='➡️ التالي',callback_data=f'browse:{uid}:{int(offset)+10}'))
    await show(c,'\n'.join(lines),InlineKeyboardMarkup(inline_keyboard=[nav,[InlineKeyboardButton(text='🔙 المحادثة',callback_data=f'chat:{uid}')]]))

@router.callback_query(F.data=='storage')
async def storage(c):
    if await guard(c,'storage'):await show(c,'🗃 التخزين والنسخ الاحتياطي\n\nالبيانات المحفوظة تبقى في Special.',storage_menu())
@router.callback_query(F.data=='backup')
async def backup(c):
    if not await guard(c,'storage.backup'):return
    await c.answer('⏳ جاري إنشاء النسخة الاحتياطية')
    try:
        path=create_full_backup(); await c.message.answer_document(FSInputFile(path),caption='💾 تم إنشاء النسخة الاحتياطية الكاملة لـ Special'); add_log('operation_log','backup_created',f'تم إنشاء نسخة احتياطية: {path.name}')
    except Exception as exc: await c.message.answer(f'❌ فشل النسخ الاحتياطي\n\n{exc}')
    await c.message.answer('💾 النسخ الاحتياطي',reply_markup=storage_menu())
@router.callback_query(F.data=='backup_choose')
async def backup_choose(c):
    if not await guard(c,'storage.backup'):return
    rows=list_private_chats(); buttons=[[InlineKeyboardButton(text=f"👤 {r['display_name'] or r['user_id']}",callback_data=f'backup:{r["user_id"]}')] for r in rows[:80]]; buttons.append([InlineKeyboardButton(text='🔙 التخزين',callback_data='storage')]); await show(c,'💾 اختر المحادثة:',InlineKeyboardMarkup(inline_keyboard=buttons))
@router.callback_query(F.data.startswith('backup:'))
async def backup_chat(c):
    if not await guard(c,'storage.backup'):return
    uid=int(c.data.split(':',1)[1]); path=create_chat_backup(uid)
    if not path: await c.answer('المحادثة غير موجودة',show_alert=True);return
    await c.message.answer_document(FSInputFile(path),caption=f'💾 نسخة محادثة {uid}'); await c.answer()

@router.callback_query(F.data=='important')
async def important(c):
    if await guard(c,'important'):await show(c,'⭐ الرسائل المهمة',important_menu())
@router.callback_query(F.data=='important_add')
async def important_add(c):
    if await guard(c,'important.add'):await show(c,'⭐ حفظ رسالة مهمة\n\nاختر الرسالة من سجل المحادثة ثم نكمل تأكيد الحفظ في الخطوة التالية.',back('important'))
@router.callback_query(F.data=='important_list')
async def important_list(c):
    if not await guard(c,'important.list'):return
    rows=important_messages(); text='⭐ الرسائل المهمة\n\n'+('لا توجد رسائل محفوظة.' if not rows else '\n\n'.join(f"🆔 {r['user_id']}\n📝 {r['text'] or '['+(r['media_type'] or 'وسائط')+']'}\n🕐 {r['message_date'] or ''}" for r in rows[:40])); await show(c,text,back('important'))

@router.callback_query(F.data=='broadcast')
async def broadcast(c):
    if await guard(c,'broadcast'): await show(c,f"📢 الإذاعة\n\n👥 المستهدفون: {len(broadcast_targets())}\n🚫 المستثنون: {len(list_broadcast_exclusions())}",broadcast_menu())
@router.callback_query(F.data=='broadcast_send')
async def broadcast_send(c):
    if await guard(c,'broadcast.create'):
        pending[user_id(c)]={'action':'broadcast_text'}; await show(c,'📢 أرسل نص الإذاعة الآن\n\nستظهر معاينة وتأكيد قبل الإرسال.',back('broadcast'))
@router.callback_query(F.data=='broadcast_cancel')
async def broadcast_cancel(c): pending.pop(user_id(c),None); await show(c,'❌ تم إلغاء الإذاعة.',broadcast_menu())
@router.callback_query(F.data=='broadcast_confirm_send')
async def broadcast_confirm_send(c):
    if not await guard(c,'broadcast.send'):return
    state=pending.pop(user_id(c),None)
    if not state or state.get('action')!='broadcast_confirm':await c.answer('لا توجد إذاعة معلقة',show_alert=True);return
    text=state.get('text','').strip(); targets=broadcast_targets(); started=datetime.now(timezone.utc).isoformat(); sent=failed=0
    await c.message.edit_text(f'📢 جاري الإرسال...\n\n👥 المستهدفون: {len(targets)}')
    for row in targets:
        try: await user_client.send_message(int(row['user_id']),text);sent+=1
        except Exception as exc: failed+=1;add_log('operation_log','broadcast_failed',f"فشل الإرسال إلى {row['user_id']}: {type(exc).__name__}")
    finished=datetime.now(timezone.utc).isoformat();add_broadcast_log(text,len(targets),sent,failed,started,finished);add_log('operation_log','broadcast_completed',f'إذاعة: المستهدفون={len(targets)} المرسل={sent} الفاشل={failed}')
    await c.message.answer(f'✅ انتهت الإذاعة\n\n👥 {len(targets)}\n✅ {sent}\n❌ {failed}',reply_markup=broadcast_menu());await c.answer()
@router.callback_query(F.data=='broadcast_exclude')
async def broadcast_exclude(c):
    if await guard(c,'broadcast.exclude'):
        pending[user_id(c)]={'action':'broadcast_exclude'};await show(c,'🚫 أرسل ID الشخص لاستثنائه من الإذاعة.',back('broadcast'))
@router.callback_query(F.data=='broadcast_exclusions')
async def broadcast_exclusions(c):
    if not await guard(c,'broadcast.exclusions'):return
    rows=list_broadcast_exclusions();text='🚫 المستثنون من الإذاعة\n\n'+('لا يوجد مستثنون.' if not rows else '\n'.join(f"{r['display_name'] or r['user_id']} — {r['user_id']}" for r in rows));await show(c,text,back('broadcast'))
@router.callback_query(F.data=='broadcast_log')
async def broadcast_log(c):
    if not await guard(c,'broadcast.log'):return
    rows=list_broadcast_logs();text='📊 سجل الإذاعات\n\n'+('لا توجد إذاعات.' if not rows else '\n\n'.join(f"🕐 {r['started_at']}\n👥 {r['total_targets']} | ✅ {r['sent_count']} | ❌ {r['failed_count']}\n📝 {r['text'][:150]}" for r in rows));await show(c,text,back('broadcast'))
@router.callback_query(F.data=='broadcast_scheduled')
async def broadcast_scheduled(c):
    if not await guard(c,'broadcast.schedule'):return
    rows=list_scheduled_broadcasts();text='📅 الإذاعات المجدولة\n\n'+('لا توجد إذاعات مجدولة.' if not rows else '\n'.join(f"#{r['id']} — {r['run_at']} — {r['status']}" for r in rows));await show(c,text,back('broadcast'))

@router.callback_query(F.data=='protection')
async def protection(c):
    if await guard(c,'protection'):await show(c,'🛡 الحماية',protection_menu())
@router.callback_query(F.data=='ownership_protection')
async def ownership(c):
    if not await guard(c,'protection.ownership'):return
    enabled=get_setting('ownership_protection','0')=='1'; await show(c,f"🛡️ الحماية من نقل الملكية\n\nالحالة: {'🟢 مفعلة' if enabled else '🔴 غير مفعلة'}\n\nيتم حفظ الإعداد والسجل؛ الإجراء التلقائي لا يُفعّل إلا بعد ربط حدث Telegram مدعوم.",kb([[InlineKeyboardButton(text='🟢 تفعيل' if not enabled else '🔴 تعطيل',callback_data='ownership_toggle')],[InlineKeyboardButton(text='📋 سجل العمليات',callback_data='security_log')],[InlineKeyboardButton(text='🔙 الحماية',callback_data='protection')]]))
@router.callback_query(F.data=='ownership_toggle')
async def ownership_toggle(c):
    if not await guard(c,'protection.ownership'):return
    enabled=get_setting('ownership_protection','0')=='1';set_setting('ownership_protection','0' if enabled else '1');add_log('security_log','ownership_protection',f"تم {'تعطيل' if enabled else 'تفعيل'} الإعداد");await ownership(c)
@router.callback_query(F.data=='media_protection')
async def media(c):
    if await guard(c,'protection.media_scan'):await show(c,'🖼️ فحص الوسائط\n\nالأرشفة متاحة. التحليل الآلي للمحتوى يحتاج محرك تحليل محتوى فعلي قبل إعطاء حكم آلي.',back('protection'))
@router.callback_query(F.data=='security_log')
async def security(c):
    if not await guard(c,'protection.log'):return
    rows=get_logs('security_log');await show(c,'📋 سجل الحماية\n\n'+('لا توجد عمليات.' if not rows else '\n'.join(f"{r['created_at']} — {r['description']}" for r in rows)),back('protection'))

@router.callback_query(F.data=='stats')
async def stats(c):
    if not await guard(c,'stats'):return
    rows=list_private_chats(); keys=['message_count','photo_count','video_count','sticker_count','gif_count','link_count','audio_count','file_count'];tot={k:sum(r[k] or 0 for r in rows) for k in keys};await show(c,f"📊 الإحصائيات\n\n👥 الأشخاص: {len(rows)}\n💬 الرسائل: {tot['message_count']}\n🖼 الصور: {tot['photo_count']}\n🎥 الفيديوهات: {tot['video_count']}\n🃏 الملصقات: {tot['sticker_count']}\n🎞 GIF: {tot['gif_count']}\n🔗 الروابط: {tot['link_count']}\n🎙 الصوتيات: {tot['audio_count']}\n📎 الملفات: {tot['file_count']}",back('main_menu'))
@router.callback_query(F.data=='search_messages')
async def search(c):
    if await guard(c,'private.search'):await show(c,'🔎 البحث في المحادثات\n\nاختر الشخص من قائمة المحادثات ثم استخدم البحث.',back('private'))
@router.callback_query(F.data=='rules')
async def rules(c):
    if await guard(c,'automation.rules'):await show(c,'🧠 القواعد والأتمتة\n\nيمكن ربط شروط حسب الشخص ونوع الرسالة والمحتوى في هذه الوحدة.',back('automation'))
@router.callback_query(F.data=='operation_log')
async def oplog(c):
    if not await guard(c,'log.operations'):return
    rows=get_logs('operation_log');await show(c,'📋 سجل العمليات\n\n'+('لا توجد عمليات.' if not rows else '\n'.join(f"{r['created_at']} — {r['description']}" for r in rows)),back('automation'))

# Developer / access management is owner-only.
@router.callback_query(F.data=='access')
async def access(c):
    if await guard(c,owner_only=True):await show(c,'👑 إدارة المستخدمين المسموحين',access_menu())
@router.callback_query(F.data=='access_add')
async def access_add(c):
    if await guard(c,owner_only=True):pending[user_id(c)]={'action':'access_add'};await show(c,'➕ أرسل ID الشخص الذي تريد السماح له.',back('access'))
@router.callback_query(F.data=='access_list')
async def access_list(c):
    if not await guard(c,owner_only=True):return
    rows=get_allowed_users();buttons=[[InlineKeyboardButton(text=f"{'🟢' if r['status']=='active' else '🔴'} {r['display_name'] or r['user_id']}",callback_data=f'access_user:{r["user_id"]}')] for r in rows[:50]];buttons.append([InlineKeyboardButton(text='🔙 رجوع',callback_data='access')]);await show(c,'👥 المستخدمون المسموحون\n\nاختر مستخدمًا:',InlineKeyboardMarkup(inline_keyboard=buttons))
@router.callback_query(F.data=='access_remove')
async def access_remove(c):
    if await guard(c,owner_only=True):pending[user_id(c)]={'action':'access_remove'};await show(c,'🗑️ أرسل ID المستخدم لإزالة صلاحية الوصول.',back('access'))
async def render_access_user(c, uid):
    r=get_allowed_user(uid)
    if not r:
        await c.answer('المستخدم غير موجود',show_alert=True); return
    await show(c,f"👤 {r['display_name'] or uid}\n🆔 {uid}\n📌 الحالة: {r['status']}\n⏱️ الصلاحية: {r['access_until'] or 'مدى الحياة'}",kb([[InlineKeyboardButton(text='🛠️ صلاحيات الميزات',callback_data=f'feature_permissions:{uid}:0')],[InlineKeyboardButton(text='⏸️ إيقاف مؤقت',callback_data=f'suspend:{uid}')],[InlineKeyboardButton(text='▶️ إعادة التفعيل',callback_data=f'resume:{uid}')],[InlineKeyboardButton(text='🚫 حظر',callback_data=f'ban:{uid}')],[InlineKeyboardButton(text='🗑️ إزالة',callback_data=f'remove:{uid}')],[InlineKeyboardButton(text='🔙 المستخدمون',callback_data='access_list')]]))

@router.callback_query(F.data.startswith('access_user:'))
async def access_user(c):
    if not await guard(c,owner_only=True):return
    uid=int(c.data.split(':')[1]); await render_access_user(c,uid)
@router.callback_query(F.data.startswith('feature_permissions:'))
async def feature_permissions(c):
    if not await guard(c,owner_only=True):return
    _,uid,page=c.data.split(':');uid=int(uid);page=int(page);r=get_allowed_user(uid)
    if not r:await c.answer('المستخدم غير موجود',show_alert=True);return
    await show(c,f"🛠️ صلاحيات الميزات\n\n👤 {r['display_name'] or uid}\n\nكل زر مستقل ويمكن السماح أو المنع لكل ميزة.",feature_permissions_menu(uid,get_feature_permissions(uid),page))
@router.callback_query(F.data.startswith('fp:'))
async def feature_toggle(c):
    if not await guard(c,owner_only=True):return
    _,uid,key,page=c.data.split(':',3);uid=int(uid);page=int(page);cur=is_feature_enabled(uid,key);set_feature_permission(uid,key,not cur);add_log('operation_log','feature_permission',f"{'سماح' if not cur else 'منع'} {key} للمستخدم {uid}");await show(c,f"🛠️ صلاحيات الميزات\n\n👤 {get_allowed_user(uid)['display_name'] or uid}\n\nتم {'السماح' if not cur else 'المنع'} لهذه الميزة.",feature_permissions_menu(uid,get_feature_permissions(uid),page))
@router.callback_query(F.data.startswith('fpp:'))
async def feature_page(c):
    if not await guard(c,owner_only=True):return
    _,uid,page=c.data.split(':');uid=int(uid);page=int(page);r=get_allowed_user(uid)
    if not r:return
    await show(c,f"🛠️ صلاحيات الميزات\n\n👤 {r['display_name'] or uid}",feature_permissions_menu(uid,get_feature_permissions(uid),page))
@router.callback_query(F.data.startswith('fpa:'))
async def feature_all(c):
    if not await guard(c,owner_only=True):return
    _,uid,flag=c.data.split(':');uid=int(uid);set_all_feature_permissions(uid,flag=='1');add_log('operation_log','feature_permissions_bulk',f"{'السماح بكل الميزات' if flag=='1' else 'منع كل الميزات'} للمستخدم {uid}");await show(c,f"🛠️ صلاحيات الميزات\n\n👤 {get_allowed_user(uid)['display_name'] or uid}",feature_permissions_menu(uid,get_feature_permissions(uid),0))
@router.callback_query(F.data.startswith('suspend:'))
async def suspend(c):
    if await guard(c,owner_only=True):
        uid=int(c.data.split(':')[1]); pending[user_id(c)]={'action':'suspend_target','target':uid};await show(c,'⏸️ اختر مدة الإيقاف:',durations_menu('suspend_duration'))
@router.callback_query(F.data.startswith('suspend_duration:'))
async def suspend_duration(c):
    if not await guard(c,owner_only=True):return
    state=pending.get(user_id(c),{});uid=state.get('target');val=c.data.split(':')[1]
    until=None if val=='life' else (datetime.now(timezone.utc)+timedelta(days=int(val))).isoformat()
    update_allowed_status(uid,'suspended',until);pending.pop(user_id(c),None);await c.answer('⏸️ تم الإيقاف');await render_access_user(c,uid)
@router.callback_query(F.data.startswith('resume:'))
async def resume(c):
    if await guard(c,owner_only=True):update_allowed_status(int(c.data.split(':')[1]),'active',None);await access_list(c)
@router.callback_query(F.data.startswith('ban:'))
async def ban(c):
    if await guard(c,owner_only=True):update_allowed_status(int(c.data.split(':')[1]),'banned',None);await access_list(c)
@router.callback_query(F.data.startswith('remove:'))
async def remove(c):
    if await guard(c,owner_only=True):remove_allowed_user(int(c.data.split(':')[1]));await access_list(c)

@router.callback_query(F.data=='settings')
async def settings(c):
    if await guard(c,'settings'):await show(c,'⚙️ الإعدادات العامة',settings_menu())
@router.callback_query(F.data=='notification_settings')
async def notif(c):
    if await guard(c,'notifications.settings'):await show(c,'🔔 إعدادات التنبيهات\n\nيمكن تخصيص التنبيهات من الإعدادات المحفوظة.',back('settings'))
@router.callback_query(F.data=='backup_settings')
async def backup_settings(c):
    if await guard(c,'settings.backup'):await show(c,'💾 إعدادات النسخ الاحتياطي\n\nالنسخ الاحتياطي الكامل يشمل قاعدة البيانات وسجل الرسائل والوسائط المحفوظة.',back('settings'))
@router.callback_query(F.data=='general_settings')
async def general_settings(c):
    if await guard(c,'settings.general'):await show(c,'⚙️ إعدادات عامة\n\nSpecial يحفظ البيانات محليًا داخل المشروع.',back('settings'))
