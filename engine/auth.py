from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthStatus:
    allowlist_enabled: bool
    allowed_count: int
    user_id: int | None = None
    authorized: bool = True


def _allowed_user_ids() -> set[int]:
    raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    if not raw:
        return set()
    values: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.add(int(part))
        except ValueError:
            continue
    return values


def is_authorized_user(user_id: int | None) -> bool:
    allowed = _allowed_user_ids()
    if not allowed:
        return True
    return user_id in allowed


def auth_status_for_user(user_id: int | None) -> AuthStatus:
    allowed = _allowed_user_ids()
    return AuthStatus(
        allowlist_enabled=bool(allowed),
        allowed_count=len(allowed),
        user_id=user_id,
        authorized=True if not allowed else user_id in allowed,
    )
