"""
Permission-checking dependency factories.

Uses the local app.core.permission_checker.PermissionChecker for permission logic.
"""

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_checker import PermissionChecker

from app.core.database import get_db
from app.core.exceptions import InsufficientPermissionsError
from app.dependencies.auth import get_current_user
from app.dependencies.tenant_scope import enforce_target_user_same_tenant
from app.models.role_name import RoleName, role_name_to_str
from app.models.user import User
from app.repositories.role_repository import RoleRepository


def require_any_role(*role_names: RoleName | str) -> Callable:
    """
    Dependency factory: requires current user to have at least one of the roles.
    Returns the full User ORM object so routes can pass it to service/helper functions.
    """
    required = [role_name_to_str(r) for r in role_names]

    async def _check(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        repo = RoleRepository(db)
        user_roles = await repo.get_user_roles(current_user.id)

        # Reuse these role names in downstream services to avoid duplicate DB queries.
        # (Routes can read `request.state.user_roles`.)
        request.state.user_roles = user_roles

        if not PermissionChecker.has_any_role(required, user_roles):
            raise InsufficientPermissionsError()

        return current_user

    return _check


def require_self_or_any_role(*role_names: RoleName | str) -> Callable:
    """
    Dependency factory for `{user_id}`-scoped routes: the caller may act on
    their own `user_id` regardless of role, or on any user's if they hold one
    of `role_names` (subject to `enforce_target_user_same_tenant`'s tenant
    scoping, using the same ADMIN/MODERATOR tenant bypass as the sibling
    role-management routes).
    """
    required = [role_name_to_str(r) for r in role_names]

    async def _check(
        request: Request,
        user_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        repo = RoleRepository(db)
        user_roles = await repo.get_user_roles(current_user.id)
        request.state.user_roles = user_roles

        if PermissionChecker.has_any_role(required, user_roles):
            await enforce_target_user_same_tenant(
                request, current_user, user_id, db, bypass_roles=(RoleName.ADMIN, RoleName.MODERATOR)
            )
            return current_user

        if user_id == current_user.id:
            return current_user

        raise InsufficientPermissionsError()

    return _check
