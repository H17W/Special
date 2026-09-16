def active_client():
    from app.user.client import active_client as _active
    return _active()


async def resolve_reply_user(event):
    from app.user.client import _resolve_reply_user
    return await _resolve_reply_user(event)
