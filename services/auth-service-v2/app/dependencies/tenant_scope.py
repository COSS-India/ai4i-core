"""Tenant scoping for auth routes: TENANT ADMIN limited to their tenant's users."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth.permission_checker import PermissionChecker
from ai4icore_multi_tenant import enforce_tenant_scope

from app.core.exceptions import EntityNotFoundError
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository


async def enforce_target_user_same_tenant(
    request: Request,
    current_user: User,
    target_user_id: int,
    db: AsyncSession,
    *,
    bypass_roles: tuple[str, ...],
) -> None:
    """Load target user and ensure TENANT ADMIN may only act on users in their tenant.

    Callers with ``bypass_roles`` (from DB role names) or ``is_superuser`` skip the check.
    """
    role_repo = RoleRepository(db)
    user_roles = await role_repo.get_user_roles(current_user.id)
    if current_user.is_superuser or PermissionChecker.has_any_role(list(bypass_roles), user_roles):
        return

    user_repo = UserRepository(db)
    target = await user_repo.get_by_id(target_user_id)
    if not target:
        raise EntityNotFoundError(f"User {target_user_id}")

    jwt_tid = getattr(request.state, "tenant_id", None)
    caller_tid = jwt_tid if jwt_tid else current_user.tenant_id_cached

    enforce_tenant_scope(
        request,
        target.tenant_id_cached,
        is_platform_admin=False,
        caller_tenant_id=str(caller_tid) if caller_tid else None,
    )
