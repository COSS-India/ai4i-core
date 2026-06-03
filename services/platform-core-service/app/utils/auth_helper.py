from fastapi import Request

from app.core.exceptions import InsufficientPermissionsError


def check_permission_ids(request: Request, *allowed: int) -> None:
    """Raise if X-Permission-Ids header does not contain any of the allowed role IDs."""
    raw = request.headers.get("X-Permission-Ids", "")
    ids = {int(p.strip()) for p in raw.split(",") if p.strip().isdigit()}
    if not ids & set(allowed):
        raise InsufficientPermissionsError()
