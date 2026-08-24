import re
from fastapi import Request

from app.core.exceptions import InsufficientPermissionsError


def _parse_permission_ids(request: Request) -> set[int]:
    raw = request.headers.get("X-Permission-Ids", "")
    return {int(m) for m in re.findall(r"\d+", raw)}


def has_permission_id(request: Request, *allowed: int) -> bool:
    """Return True if X-Permission-Ids header contains any of the given IDs."""
    return bool(_parse_permission_ids(request) & set(allowed))


def check_permission_ids(request: Request, *allowed: int) -> None:
    """Raise if X-Permission-Ids header does not contain any of the allowed role IDs."""
    if not has_permission_id(request, *allowed):
        raise InsufficientPermissionsError()
