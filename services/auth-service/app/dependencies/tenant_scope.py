"""Tenant scoping for auth routes: TENANT ADMIN limited to their tenant's users."""

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_checker import PermissionChecker

from app.core.exceptions import EntityNotFoundError
from app.models.role_name import RoleName, role_name_to_str
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository


async def enforce_target_user_same_tenant(
    request: Request,
    current_user: User,
    target_user_id,
    db: AsyncSession,
    *,
    bypass_roles: tuple[RoleName | str, ...],
) -> User:
    """Load target user and ensure tenant admin may only act on users in their tenant.

    Callers with any role in ``bypass_roles`` skip the tenant check but the
    target user is still loaded and returned.
    """
    user_repo = UserRepository(db)
    target = await user_repo.get_by_id(target_user_id)
    if not target:
        raise EntityNotFoundError(f"User {target_user_id}")

    role_repo = RoleRepository(db)
    user_roles = await role_repo.get_user_roles(current_user.id)
    if PermissionChecker.has_any_role([role_name_to_str(r) for r in bypass_roles], user_roles):
        return target

    jwt_tid = getattr(request.state, "tenant_id", None)
    try:
        caller_tid = int(jwt_tid) if jwt_tid else current_user.tenant_id
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Your session token contains an invalid tenant context. Please sign in again."},
        ) from exc

    if not caller_tid or caller_tid != target.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_FORBIDDEN",
                "message": "Cannot access user outside your tenant.",
            },
        )
    return target
