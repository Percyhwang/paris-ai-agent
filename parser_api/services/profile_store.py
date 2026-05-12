from __future__ import annotations

from copy import deepcopy

CURRENT_USER_PROFILE: dict[str, object] = {}


def get_user_profile() -> dict[str, object]:
    return deepcopy(CURRENT_USER_PROFILE)


def update_user_profile(profile_payload: dict[str, object]) -> dict[str, object]:
    for key, value in profile_payload.items():
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        CURRENT_USER_PROFILE[key] = deepcopy(value)
    return get_user_profile()


def reset_user_profile() -> None:
    CURRENT_USER_PROFILE.clear()
