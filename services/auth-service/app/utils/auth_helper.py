import re
from fastapi import Request

from app.core.config import RoleName
from app.core.exceptions import InsufficientPermissionsError


def role_name_to_str(name: RoleName | str) -> str:
    """Normalize ORM enum members or API strings to plain str."""
    return name.value if isinstance(name, RoleName) else name


def check_permission_ids(request: Request, *allowed: int) -> None:
    """Raise if X-Permission-Ids header does not contain any of the allowed role IDs."""
    raw = request.headers.get("X-Permission-Ids", "")
    ids = {int(m) for m in re.findall(r"\d+", raw)}
    if not ids & set(allowed):
        raise InsufficientPermissionsError()
