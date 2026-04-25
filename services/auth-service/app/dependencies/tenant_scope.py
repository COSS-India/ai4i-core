"""Tenant scoping for auth routes: TENANT ADMIN limited to their tenant's users."""

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth.permission_checker import PermissionChecker

from app.core.exceptions import EntityNotFoundError
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository


async def enforce_target_user_same_tenant(
    request: Request,
    current_user: User,
    target_user_id,
    db: AsyncSession,
    *,
    bypass_roles: tuple[str, ...],
) -> None:
    """Load target user and ensure tenant admin may only act on users in their tenant.

    Callers with any role in ``bypass_roles`` skip the check.
    """
    role_repo = RoleRepository(db)
    user_roles = await role_repo.get_user_roles(current_user.user_id)
    if PermissionChecker.has_any_role(list(bypass_roles), user_roles):
        return

    user_repo = UserRepository(db)
    target = await user_repo.get_by_id(target_user_id)
    if not target:
        raise EntityNotFoundError(f"User {target_user_id}")

    jwt_tid = getattr(request.state, "tenant_id", None)
    caller_tid = jwt_tid if jwt_tid else current_user.tenant_id

    target_tid = str(target.tenant_id) if target.tenant_id else None
    caller_tid_str = str(caller_tid) if caller_tid else None

    if not caller_tid_str or caller_tid_str != target_tid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_FORBIDDEN",
                "message": "Cannot access user outside your tenant.",
            },
        )
