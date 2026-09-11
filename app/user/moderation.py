from app.core.database import (
    get_all_muted_users,
    is_muted,
    mute_user,
    unmute_user,
)


def mute(
    user_id: int,
    username: str | None,
    display_name: str | None,
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
