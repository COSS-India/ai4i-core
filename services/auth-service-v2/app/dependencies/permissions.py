"""
Permission-checking dependency factories.

Uses the shared ai4icore_auth.PermissionChecker for all permission logic.
No service-local permission implementation.
"""

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth.permission_checker import PermissionChecker

from app.core.database import get_db
from app.core.exceptions import InsufficientPermissionsError
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.repositories.role_repository import RoleRepository


def require_permission(resource: str, action: str) -> Callable:
    """
    Dependency factory: requires current user to have (resource.action) permission.
    Uses shared PermissionChecker — same logic across all services.
    """

    async def _check(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if current_user.is_superuser:
            return current_user

        repo = RoleRepository(db)
        permission_names = await repo.get_user_permission_names(current_user.id)
        required = f"{resource}.{action}"

        if not PermissionChecker.has_permission(required, permission_names):
            raise InsufficientPermissionsError(resource, action)

        return current_user

    return _check


def require_any_role(*role_names: str) -> Callable:
    """
    Dependency factory: requires current user to have at least one of the roles.
    Uses shared PermissionChecker.has_any_role.
    """

    async def _check(
        request: Request,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if current_user.is_superuser:
            return current_user

        repo = RoleRepository(db)
        user_roles = await repo.get_user_roles(current_user.id)

        # Reuse these role names in downstream services to avoid duplicate DB queries.
        # (Routes can read `request.state.user_roles`.)
        request.state.user_roles = user_roles

        if not PermissionChecker.has_any_role(list(role_names), user_roles):
            raise InsufficientPermissionsError()

        return current_user

    return _check
