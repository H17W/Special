from app.user.moderation import mute, unmute, mute_in_chat, unmute_in_chat
from app.core.database import get_chat_muted_user_by_username
from app.user.client_runtime import active_client, resolve_reply_user


async def _target_from_reply(event):
    target, target_id = await resolve_reply_user(event)
    if target_id is None:
        return None, None
    if target is None:
        try:
            target = await active_client().get_entity(target_id)
        except Exception:
            target = type("ReplyTarget", (), {"id": target_id})()
    return target, int(target_id)


async def handle_moderation_command(event, text: str) -> bool:
    """Handle only exact mute/unmute commands; never consume unrelated text."""
    lower = (text or '').strip().lower()

    if lower in {'.كتم', 'كتم', '/كتم', '.mute', 'mute'}:
        if not event.is_reply:
            await event.edit('⚠️ رد على رسالة المستخدم أولًا ثم أرسل أمر الكتم')
            return True
        replied = await event.get_reply_message()
        target = await replied.get_sender() if replied else None
        if not target:
            await event.edit('⚠️ لم أستطع تحديد صاحب الرسالة')
            return True
        if event.is_private:
            # Private mute is global for the person. Do not write it into the
            # chat-specific table, otherwise private unmute cannot remove it.
            mute(int(target.id), getattr(target, 'username', None), getattr(target, 'first_name', None) or getattr(target, 'last_name', None))
        else:
            try:
                entity = await active_client().get_entity(event.chat_id)
                me = await active_client().get_me()
                perms = await active_client().get_permissions(entity, me)
                if not getattr(perms, 'is_creator', False) and not getattr(perms, 'delete_messages', False):
                    await event.edit('❌ تعذر المسح ليس لديك صلاحية حذف رسائل الاخرين')
                    return True
            except Exception:
                await event.edit('❌ تعذر المسح ليس لديك صلاحية حذف رسائل الاخرين')
                return True
            mute_in_chat(int(event.chat_id), int(target.id), getattr(target, 'username', None), getattr(target, 'first_name', None) or getattr(target, 'last_name', None))
        await event.edit('🔇 تم كتم هذا الشخص')
        return True

    if lower in {'.فك', 'فك', '/فك', '.unmute', 'unmute', 'الغاء الكتم', 'إلغاء الكتم', '/الغاء الكتم', '/إلغاء الكتم'}:
        target, target_id = await _target_from_reply(event) if event.is_reply else (None, None)
        if target_id is None:
            parts = lower.split(maxsplit=1)
            argument = parts[1].strip() if len(parts) > 1 else ''
            if not argument:
                await event.edit('⚠️ رد على رسالة الشخص المكتوم أولًا أو اكتب الـ ID أو المنشن')
                return True
            try:
                if argument.lstrip('-').isdigit():
                    target = await active_client().get_entity(int(argument))
                else:
                    target = await active_client().get_entity(argument.lstrip('@'))
                target_id = int(target.id)
            except Exception:
                target = None
            if target is None and not event.is_private:
                row = get_chat_muted_user_by_username(int(event.chat_id), argument.lstrip('@'))
                if row:
                    target_id = int(row['user_id'])
            if target_id is None:
                await event.edit('⚠️ لم أستطع تحديد المستخدم من الـ ID أو المنشن')
                return True

        if event.is_private:
            ok = unmute(target_id)
        else:
            ok = unmute_in_chat(int(event.chat_id), target_id)
        await event.edit('🔊 تم الغاء الكتم عن هذا المستخدم' if ok else 'ℹ️ المستخدم غير موجود في قائمة المكتومين')
        return True

    return False
