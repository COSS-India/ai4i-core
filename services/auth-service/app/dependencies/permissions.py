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
from app.dependencies.auth import get_current_user_id
from app.models.role_name import RoleName, role_name_to_str
from app.repositories.role_repository import RoleRepository


def require_any_role(*role_names: RoleName | str) -> Callable:
    """
    Dependency factory: requires current user to have at least one of the roles.
    Uses shared PermissionChecker.has_any_role.
    """
    required = [role_name_to_str(r) for r in role_names]

    async def _check(
        request: Request,
        user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
    ) -> UUID:
        repo = RoleRepository(db)
        user_roles = await repo.get_user_roles(user_id)

        # Reuse these role names in downstream services to avoid duplicate DB queries.
        # (Routes can read `request.state.user_roles`.)
        request.state.user_roles = user_roles

        if not PermissionChecker.has_any_role(required, user_roles):
            raise InsufficientPermissionsError()

        return user_id

    return _check
