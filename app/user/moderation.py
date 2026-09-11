from app.core.database import (
    mute_user,
    unmute_user,
    is_muted,
)


def mute(user_id: int, username: str | None, display_name: str | None):
    mute_user(
        user_id=user_id,
        username=username,
        display_name=display_name,
    )


def unmute(user_id: int) -> bool:
    return unmute_user(user_id)


def check_muted(user_id: int) -> bool:
    return is_muted(user_id)
