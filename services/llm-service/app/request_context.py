"""Helpers for mapping auth request.state into DB-safe values."""

from typing import Optional

from starlette.requests import Request


def optional_db_user_id(request: Request) -> Optional[int]:
    """
    llm_requests.user_id is an FK to users.id (integer).

    JWT sub or API-key metadata may carry a UUID string; never pass that to int FK columns.
    """
    uid = getattr(request.state, "user_id", None)
    if isinstance(uid, int) and uid > 0:
        return uid
    if isinstance(uid, str) and uid.isdigit():
        return int(uid)
    return None
