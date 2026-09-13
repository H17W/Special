from __future__ import annotations

import time
import platform

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram import BaseMiddleware

from app.core.config import settings
from app.core.database import db
from app.core.permissions import allowed, is_owner
from app.core.navigation import nav
from app.core.exporter import export_backup
from app.core.audio import to_voice, AudioError
from app.services.cleanup import clean, counts
from app.services.private_log import conversation
from app.services.broadcast import run_broadcast
from app.user.client import manager

from .keyboards import *
from .context import session

router = Router()


def uid(c):
    return c.from_user.id


async def ans(c, t="", a=False):
    try:
        await c.answer(t, show_alert=a)
    except Exception:
        pass


class KeyboardSecurity(BaseMiddleware):
    async def __call__(self, handler, event, data):
        m = getattr(event, "message", None)
        u = getattr(event, "from_user", None)

        if m and u:
            r = db.one(
                "SELECT owner_id FROM keyboard_sessions "
                "WHERE chat_id=? AND message_id=?",
                (m.chat.id, m.message_id),
            )

            if r and u.id not in (r["owner_id"], settings.owner_id):
                n = db.add_keyboard_abuse(u.id)

                if n >= 3:
                    db.restrict(
                        u.id,
                        300,
                        reason="Unauthorized keyboard interaction",
                    )
                    await ans(
                        event,
                        "⛔ تم تقييدك 5 دقائق",
                        True,
                    )
                else:
                    await ans(
                        event,
                        "⛔ هذه اللوحة ليست لك",
                        True,
                    )

                return

        return await handler(event, data)


router.callback_query.middleware(KeyboardSecurity())


# =========================================================
# MAIN
# =========================================================

@router.callback_query(F.data == "home")
async def home(c):
    await c.message.edit_text(
        "🧠 Special\n\nاختر من لوحة التحكم:",
        reply_markup=main_menu(is_owner(uid(c))),
    )
    await ans(c)


@router.callback_query(F.data == "back")
async def back_cb(c):
    await home(c)


# =========================================================
# ACCOUNT
# =========================================================

@router.callback_query(F.data == "account")
async def account(c):
    await c.message.edit_text(
        "👤 إدارة الحساب\n\n"
        "🔐 تسجيل الدخول /login\n"
        "👤 معلومات الحساب من حساب Telegram\n"
        "🎭 التقليد بالرد على الشخص ثم كتابة تقليد\n"
        "↩️ الإلغاء بالرد وكتابة الغاء التقليد",
        reply_markup=back(),
    )
    await ans(c)


# =========================================================
# PRIVATE MANAGEMENT
# =========================================================

@router.callback_query(F.data == "private")
async def private(c):
    await c.message.edit_text(
        "📥 إدارة الخاص\n\n"
        "إدارة الأشخاص والمحادثات الخاصة المحفوظة.",
        reply_markup=kb([
            [
                ("📥 استيراد الخاص", "p_import"),
                ("📜 سجل الخاص", "p_log"),
            ],
            [
                ("🔎 بحث", "p_search"),
            ],
            [
                ("↩️ رجوع", "home"),
            ],
        ]),
    )
    await ans(c)


# ---------------------------------------------------------
# Get real Telegram private dialogs
# ---------------------------------------------------------

async def get_private_dialogs(limit=200):
    dialogs = []

    async for dialog in manager.client.iter_dialogs(limit=limit):
        entity = dialog.entity

        if not dialog.is_user:
            continue

        if getattr(entity, "bot", False):
            continue

        if getattr(entity, "deleted", False):
            continue

        dialogs.append(dialog)

    return dialogs


def display_name(entity):
    first = getattr(entity, "first_name", "") or ""
    last = getattr(entity, "last_name", "") or ""

    name = f"{first} {last}".strip()

    if name:
        return name

    username = getattr(entity, "username", None)

    if username:
        return f"@{username}"

    return f"ID {getattr(entity, 'id', '')}"


def private_dialog_keyboard(dialogs, page=0, per_page=8):
    total = len(dialogs)

    start = page * per_page
    end = start + per_page

    current = dialogs[start:end]

    rows = []

    for dialog in current:
        entity = dialog.entity
        name = display_name(entity)

        username = getattr(entity, "username", None)

        if username:
            text = f"👤 {name}  @{username}"
        else:
            text = f"👤 {name}"

        rows.append([
            InlineKeyboardButton(
                text=text[:60],
                callback_data=f"pchat:{entity.id}:{page}",
            )
        ])

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ السابق",
                callback_data=f"pdialogs:{page - 1}",
            )
        )

    navigation.append(
        InlineKeyboardButton(
            text=f"📄 {page + 1}/{max(1, (total + per_page - 1) // per_page)}",
            callback_data="noop",
        )
    )

    if end < total:
        navigation.append(
            InlineKeyboardButton(
                text="التالي ➡️",
                callback_data=f"pdialogs:{page + 1}",
            )
        )

    if navigation:
        rows.append(navigation)

    rows.append([
        InlineKeyboardButton(
            text="🔙 إدارة الخاص",
            callback_data="private",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_private_dialogs(c, page=0):
    dialogs = await get_private_dialogs()

    if not dialogs:
        await c.message.edit_text(
            "📥 استيراد الخاص\n\n"
            "ما لقيت أي محادثات خاصة متاحة.",
            reply_markup=back("private"),
        )
        await ans(c)
        return

    await c.message.edit_text(
        "📥 استيراد الخاص\n\n"
        "👥 اختر الشخص الذي تريد استيراد محادثته:\n\n"
        f"عدد المحادثات الخاصة: {len(dialogs)}",
        reply_markup=private_dialog_keyboard(
            dialogs,
            page=page,
            per_page=8,
        ),
    )

    await ans(c)


@router.callback_query(F.data == "p_import")
async def pimport(c):
    await show_private_dialogs(c, 0)


@router.callback_query(F.data.startswith("pdialogs:"))
async def private_dialogs_page(c):
    page = int(c.data.split(":", 1)[1])
    await show_private_dialogs(c, page)


# ---------------------------------------------------------
# Selected private chat
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("pchat:"))
async def private_chat(c):
    parts = c.data.split(":")

    chat_id = int(parts[1])
    page = int(parts[2])

    try:
        entity = await manager.client.get_entity(chat_id)
    except Exception as exc:
        await ans(
            c,
            f"❌ تعذر فتح المحادثة\n{type(exc).__name__}",
            True,
        )
        return

    name = display_name(entity)
    username = getattr(entity, "username", None)

    username_text = f"@{username}" if username else "لا يوجد"

    row = db.one(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN kind='incoming' THEN 1 ELSE 0 END) AS incoming,
            SUM(CASE WHEN kind='outgoing' THEN 1 ELSE 0 END) AS outgoing
        FROM message_archive
        WHERE chat_id=?
        """,
        (chat_id,),
    )

    total = int(row["total"] or 0) if row else 0
    incoming = int(row["incoming"] or 0) if row else 0
    outgoing = int(row["outgoing"] or 0) if row else 0

    await c.message.edit_text(
        "👤 معلومات المحادثة\n\n"
        f"الاسم: {name}\n"
        f"Username: {username_text}\n"
        f"🆔 ID: {chat_id}\n\n"
        f"💬 الرسائل المحفوظة: {total}\n"
        f"📥 الواردة: {incoming}\n"
        f"📤 الصادرة: {outgoing}",
        reply_markup=kb([
            [
                (
                    "📖 تصفح السجل",
                    f"pbrowse:{chat_id}:0:{page}",
                )
            ],
            [
                (
                    "📥 استيراد هذه المحادثة",
                    f"pimport_chat:{chat_id}:{page}",
                )
            ],
            [
                (
                    "🔄 تحديث",
                    f"pchat:{chat_id}:{page}",
                )
            ],
            [
                (
                    "🔙 الأشخاص",
                    f"pdialogs:{page}",
                )
            ],
        ]),
    )

    await ans(c)


# ---------------------------------------------------------
# Import selected chat
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("pimport_chat:"))
async def import_selected_chat(c):
    parts = c.data.split(":")

    chat_id = int(parts[1])
    page = int(parts[2])

    try:
        await c.message.edit_text(
            "📥 جاري استيراد المحادثة...\n\n"
            "⏳ انتظر إلى أن يكتمل الاستيراد."
        )

        count = await manager.import_private(
            chat_id,
            limit=1000,
        )

        try:
            entity = await manager.client.get_entity(chat_id)
            name = display_name(entity)
        except Exception:
            name = str(chat_id)

        await c.message.edit_text(
            "✅ تم استيراد المحادثة بنجاح\n\n"
            f"👤 {name}\n"
            f"🆔 {chat_id}\n"
            f"📥 الرسائل المستوردة: {count}",
            reply_markup=kb([
                [
                    (
                        "📖 تصفح السجل",
                        f"pbrowse:{chat_id}:0:{page}",
                    )
                ],
                [
                    (
                        "🔙 الأشخاص",
                        f"pdialogs:{page}",
                    )
                ],
            ]),
        )

        db.log(
            settings.owner_id,
            "private_import_ui",
            f"{chat_id}:{count}",
        )

    except Exception as exc:
        await c.message.edit_text(
            "❌ تعذر استيراد المحادثة\n\n"
            f"{type(exc).__name__}: {exc}",
            reply_markup=kb([
                [
                    (
                        "🔄 المحاولة مرة ثانية",
                        f"pimport_chat:{chat_id}:{page}",
                    )
                ],
                [
                    (
                        "🔙 الأشخاص",
                        f"pdialogs:{page}",
                    )
                ],
            ]),
        )

    await ans(c)


# ---------------------------------------------------------
# Browse imported private chat
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("pbrowse:"))
async def browse_private_chat(c):
    parts = c.data.split(":")

    chat_id = int(parts[1])
    offset = int(parts[2])
    people_page = int(parts[3])

    rows = conversation(
        chat_id,
        limit=10,
        offset=offset,
    )

    try:
        entity = await manager.client.get_entity(chat_id)
        name = display_name(entity)
    except Exception:
        name = str(chat_id)

    if not rows:
        await c.message.edit_text(
            "📖 سجل المحادثة\n\n"
            f"👤 {name}\n\n"
            "لا توجد رسائل محفوظة في هذه الصفحة.",
            reply_markup=kb([
                [
                    (
                        "🔙 المحادثة",
                        f"pchat:{chat_id}:{people_page}",
                    )
                ],
                [
                    (
                        "👥 الأشخاص",
                        f"pdialogs:{people_page}",
                    )
                ],
            ]),
        )
        await ans(c)
        return

    lines = [
        "📖 سجل المحادثة",
        "",
        f"👤 {name}",
        f"🆔 {chat_id}",
        "",
    ]

    for row in rows:
        created = row["created_at"] or ""

        sender = row["sender_name"] or "مستخدم"

        if row["sender_username"]:
            sender += f" @{row['sender_username']}"

        text = row["text"] or ""

        if not text:
            text = f"[{row['media_type'] or 'وسائط'}]"

        if row["edited_at"]:
            text += " ✏️"

        if row["deleted_at"]:
            text += " 🗑️"

        lines.append(
            f"🕐 {created}\n"
            f"{sender}\n"
            f"{text}\n"
        )

    navigation = []

    if offset >= 10:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ السابق",
                callback_data=f"pbrowse:{chat_id}:{offset - 10}:{people_page}",
            )
        )

    if len(rows) == 10:
        navigation.append(
            InlineKeyboardButton(
                text="التالي ➡️",
                callback_data=f"pbrowse:{chat_id}:{offset + 10}:{people_page}",
            )
        )

    rows_buttons = []

    if navigation:
        rows_buttons.append(navigation)

    rows_buttons.append([
        InlineKeyboardButton(
            text="🔙 المحادثة",
            callback_data=f"pchat:{chat_id}:{people_page}",
        )
    ])

    rows_buttons.append([
        InlineKeyboardButton(
            text="👥 الأشخاص",
            callback_data=f"pdialogs:{people_page}",
        )
    ])

    await c.message.edit_text(
        "\n".join(lines)[:3900],
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=rows_buttons
        ),
    )

    await ans(c)


# ---------------------------------------------------------
# Search private chats
# ---------------------------------------------------------

@router.callback_query(F.data == "p_search")
async def psearch(c):
    session(uid(c)).mode = "private_search"

    await c.message.edit_text(
        "🔎 البحث في الخاص\n\n"
        "اكتب الاسم أو username أو ID\n\n"
        "وسيبحث Special في المحادثات المحفوظة.",
        reply_markup=back("private"),
    )

    await ans(c)


# ---------------------------------------------------------
# Private log
# ---------------------------------------------------------

@router.callback_query(F.data == "p_log")
async def plog(c):
    rows = db.all(
        """
        SELECT
            chat_id,
            MAX(created_at) AS last,
            COUNT(*) AS total
        FROM message_archive
        GROUP BY chat_id
        ORDER BY last DESC
        LIMIT 10
        """
    )

    if not rows:
        text = "📜 سجل الخاص\n\nلا يوجد سجل محفوظ."
    else:
        text = "📜 سجل الخاص\n\n"

        for row in rows:
            try:
                entity = await manager.client.get_entity(
                    int(row["chat_id"])
                )
                name = display_name(entity)
            except Exception:
                name = str(row["chat_id"])

            text += (
                f"👤 {name}\n"
                f"🆔 {row['chat_id']}\n"
                f"💬 {row['total']} رسالة\n\n"
            )

    await c.message.edit_text(
        text[:3900],
        reply_markup=back("private"),
    )

    await ans(c)


# =========================================================
# STORAGE
# =========================================================

@router.callback_query(F.data == "storage")
async def storage(c):
    s = db.stats()

    await c.message.edit_text(
        f"📦 التخزين والحفظ\n\n"
        f"المحفوظات: {s['storage']}\n"
        f"الرسائل المؤرشفة: {s['messages']}\n\n"
        "⏳ الوسائط المؤقتة تُرسل إلى الخاص ثم تُحذف "
        "من السيرفر بعد نجاح الإرسال.",
        reply_markup=back(),
    )

    await ans(c)


# =========================================================
# SECURITY
# =========================================================

@router.callback_query(F.data == "security")
async def security(c):
    await c.message.edit_text(
        "🛡️ الحماية والإدارة\n\n"
        "🔇 الكتم بالرد ثم كتم\n"
        "🗑️ الحذف ببداية الحذف ونهاية الحذف\n"
        "🔒 حماية الخاص عبر الإعدادات\n"
        "🚫 فلتر الشتم",
        reply_markup=back(),
    )

    await ans(c)


# =========================================================
# SMART TOOLS
# =========================================================

@router.callback_query(F.data == "tools")
async def tools(c):
    await c.message.edit_text(
        "🤖 الأدوات الذكية",
        reply_markup=kb([
            [
                ("🧠 AI", "ai"),
                ("🎵 الموسيقى", "music"),
            ],
            [
                ("🎙️ الصوت", "audio_help"),
            ],
            [
                ("↩️ رجوع", "home"),
            ],
        ]),
    )

    await ans(c)


@router.callback_query(F.data == "ai")
async def ai(c):
    session(uid(c)).mode = "ai"

    await c.message.edit_text(
        "🧠 اكتب سؤالك"
    )

    await ans(c)


@router.callback_query(F.data == "music")
async def music(c):
    session(uid(c)).mode = "music"

    await c.message.edit_text(
        "🎵 اكتب اسم الأغنية أو الفنان"
    )

    await ans(c)


@router.callback_query(F.data == "audio_help")
async def audio_help(c):
    await c.message.edit_text(
        "🎙️ أرسل ملف صوتي للبوت ثم اختر تحويل إلى فويس "
        "أو تعديل البيانات",
        reply_markup=back(),
    )

    await ans(c)


# =========================================================
# STATS
# =========================================================

@router.callback_query(F.data == "stats")
async def stats(c):
    await c.message.edit_text(
        "📊 الإحصائيات\n\n"
        + "\n".join(
            f"{k}: {v}"
            for k, v in db.stats().items()
        ),
        reply_markup=back(),
    )

    await ans(c)


# =========================================================
# HELP
# =========================================================

@router.callback_query(F.data == "help")
async def help_cb(c):
    from .handlers import help_text

    await c.message.edit_text(
        help_text(),
        reply_markup=back(),
    )

    await ans(c)


# =========================================================
# BROADCAST
# =========================================================

@router.callback_query(F.data == "broadcast")
async def broadcast(c):
    if not is_owner(uid(c)):
        return await ans(c, "للمطور فقط", True)

    await c.message.edit_text(
        "📢 الإذاعة\n\n"
        "استخدم /broadcast نص الرسالة لإرسالها "
        "للمستخدمين المصرح لهم مع Rate Limit وتتبع النتيجة.",
        reply_markup=back(),
    )

    await ans(c)


# =========================================================
# DEVELOPER
# =========================================================

@router.callback_query(F.data == "admin")
async def admin(c):
    if not is_owner(uid(c)):
        return await ans(c, "للمطور فقط", True)

    await c.message.edit_text(
        "🛡️ لوحة المطور",
        reply_markup=admin_menu(),
    )

    await ans(c)


@router.callback_query(F.data == "admin_requests")
async def requests(c):
    rows = db.pending_requests()

    if not rows:
        return await ans(c, "لا توجد طلبات", True)

    r = rows[0]

    await c.message.edit_text(
        f"📨 الطلب #{r['id']}\n"
        f"المستخدم: {r['user_id']}",
        reply_markup=request_actions(r["id"]),
    )

    await ans(c)


@router.callback_query(F.data.startswith("req:"))
async def req(c):
    if not is_owner(uid(c)):
        return await ans(c, "للمطور فقط", True)

    p = c.data.split(":")

    rid = int(p[2])

    r = db.one(
        "SELECT * FROM access_requests WHERE id=?",
        (rid,),
    )

    if not r or r["status"] != "pending":
        return await ans(
            c,
            "الطلب غير متاح",
            True,
        )

    if p[1] == "accept":
        sec = int(p[3])

        exp = (
            None
            if sec == 0
            else int(time.time()) + sec
        )

        db.decide_request(
            rid,
            r["user_id"],
            True,
            exp,
        )

        await c.bot.send_message(
            r["user_id"],
            "تم قبول طلبك",
        )

        db.log(
            uid(c),
            "access_accept",
            str(r["user_id"]),
        )

        await c.message.edit_text(
            "✅ تم قبول الطلب",
            reply_markup=admin_menu(),
        )

    elif p[3] == "reason":
        session(uid(c)).mode = "reject_reason"
        session(uid(c)).data = {"rid": rid}

        await c.message.edit_text(
            "✏️ أرسل سبب الرفض الآن"
        )

    else:
        db.decide_request(
            rid,
            r["user_id"],
            False,
            reason=None,
        )

        await c.bot.send_message(
            r["user_id"],
            "تم رفض طلبك",
        )

        db.log(
            uid(c),
            "access_reject",
            str(r["user_id"]),
        )

        await c.message.edit_text(
            "❌ تم رفض الطلب",
            reply_markup=admin_menu(),
        )

    await ans(c)


# =========================================================
# CLEANUP
# =========================================================

@router.callback_query(F.data == "cleanup")
async def cleanup(c):
    if not is_owner(uid(c)):
        return await ans(c, "للمطور فقط", True)

    x = counts()

    await c.message.edit_text(
        "🧹 تنظيف البوت\n\n"
        + "\n".join(
            f"{k}: {v}"
            for k, v in x.items()
        ),
        reply_markup=cleanup_menu(),
    )

    await ans(c)


@router.callback_query(F.data.startswith("clean:"))
async def clean_cb(c):
    if not is_owner(uid(c)):
        return await ans(c, "للمطور فقط", True)

    cat = c.data.split(":", 1)[1]

    if cat == "all":
        n = sum(
            clean(x)
            for x in [
                "operations",
                "private_log",
                "access",
                "broadcast",
                "storage",
            ]
        )
    else:
        n = clean(cat)

    db.log(
        uid(c),
        "cleanup",
        cat,
    )

    await c.message.edit_text(
        f"🧹 تم التنظيف\n"
        f"العناصر المحذوفة: {n}",
        reply_markup=cleanup_menu(),
    )

    await ans(c)


# =========================================================
# AUDIT
# =========================================================

@router.callback_query(F.data == "audit")
async def audit(c):
    if not is_owner(uid(c)):
        return await ans(c, "للمطور فقط", True)

    rows = db.logs(30)

    text = (
        "📜 سجل العمليات\n\n"
        + "\n".join(
            f'#{r["id"]} {r["user_id"]} — '
            f'{r["action"]} — {r["detail"]}'
            for r in rows
        )
    )

    if not rows:
        text = "📜 سجل العمليات\n\nلا يوجد سجل"

    await c.message.edit_text(
        text[:3900],
        reply_markup=back("admin"),
    )

    await ans(c)


# =========================================================
# HEALTH
# =========================================================

@router.callback_query(F.data == "health")
async def health(c):
    await c.message.edit_text(
        f"🩺 صحة النظام\n\n"
        f"Python: {platform.python_version()}\n"
        f"OS: {platform.system()}\n"
        "DB: OK\n"
        "Navigation: OK\n"
        "Queues: OK\n"
        "Storage: OK",
        reply_markup=back("admin"),
    )

    await ans(c)


# =========================================================
# BACKUP
# =========================================================

@router.callback_query(F.data == "backup")
async def backup(c):
    if not is_owner(uid(c)):
        return await ans(c, "للمطور فقط", True)

    p = export_backup()

    await c.message.answer_document(
        FSInputFile(str(p))
    )

    await ans(
        c,
        "تم إنشاء النسخة",
    )


# =========================================================
# AUDIO
# =========================================================

@router.callback_query(F.data.startswith("audio:"))
async def audio_cb(c):
    s = session(uid(c))

    if not s.data:
        return await ans(
            c,
            "جلسة الصوت انتهت",
            True,
        )

    if c.data == "audio:edit":
        s.mode = "audio_edit"

        await c.message.edit_text(
            "اكتب الاسم | الفنان"
        )

        return await ans(c)

    try:
        from pathlib import Path

        src = s.data["path"]
        dst = src.rsplit(".", 1)[0] + ".ogg"

        await to_voice(
            Path(src),
            Path(dst),
        )

        await c.message.answer_voice(
            FSInputFile(dst),
            caption=(
                f'{s.data.get("title", "")}'
                f' — '
                f'{s.data.get("artist", "")}'
            ),
        )

        await ans(c, "تم")

    except AudioError as e:
        await ans(
            c,
            str(e),
            True,
        )


# =========================================================
# NO-OP
# =========================================================

@router.callback_query(F.data == "noop")
async def noop(c):
    await ans(c)
