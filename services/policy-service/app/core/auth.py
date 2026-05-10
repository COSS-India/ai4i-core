from __future__ import annotations

from typing import Optional
from fastapi import Header, HTTPException, Request, status


async def require_adopter_admin(
    request: Request,
    x_roles: Optional[str] = Header(None, alias="X-Roles"),
) -> None:
    """
    Enforce Adopter Admin access (platform admin).

    Auth validation is delegated to API gateway. Services read pre-validated
    identity headers. Convention: "ADMIN" is platform-wide admin.
    """
    roles = (x_roles or "").split(",") if x_roles else []
    if "ADMIN" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Adopter admin privileges required",
            },
        )
    request.state.is_platform_admin = True

