from app.core.database import (
    get_all_muted_users,
    is_muted,
    mute_user,
    unmute_user,
)


def mute(
    user_id: int,
    username: str | None = None,
    display_name: str | None = None,
):
    mute_user(
        user_id=user_id,
        username=username,
        display_name=display_name,
    )


def unmute(user_id: int) -> bool:
    return unmute_user(user_id)


def check_muted(user_id: int) -> bool:
    return is_muted(user_id)


def muted_users():
    return get_all_muted_users()


def mute_in_chat(chat_id: int, user_id: int, username: str | None = None, display_name: str | None = None):
    from app.core.database import mute_user_in_chat
    mute_user_in_chat(chat_id, user_id, username, display_name)


def unmute_in_chat(chat_id: int, user_id: int) -> bool:
    from app.core.database import unmute_user_in_chat
    return unmute_user_in_chat(chat_id, user_id)


def is_muted_in_chat(chat_id: int, user_id: int) -> bool:
    from app.core.database import is_user_muted_in_chat
    return is_user_muted_in_chat(chat_id, user_id)
