"""
User CRUD business logic.
"""

import logging
from typing import Optional

from app.core.exceptions import AuthorizationError
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, user_repo: UserRepository, role_repo: RoleRepository) -> None:
        self._users = user_repo
        self._roles = role_repo

    async def get_user_profile(self, user: User) -> dict:
        """Get user profile with roles."""
        roles = await self._roles.get_user_roles(user.id)
        return {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_superuser": user.is_superuser,
            "is_tenant": user.is_tenant,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "last_login": user.last_login,
            "avatar_url": user.avatar_url,
            "phone_number": user.phone_number,
            "timezone": user.timezone,
            "language": user.language,
            "roles": roles,
            "tenant_id": user.tenant_id_cached,
        }

    async def update_profile(self, user: User, data: dict) -> User:
        """Update user profile fields."""
        await self._users.update(user, data)
        await self._users.commit()
        return user

    async def list_users(self, offset: int = 0, limit: int = 100) -> list[User]:
        return await self._users.list_all(offset, limit)

    async def list_users_for_caller(
        self,
        caller: User,
        offset: int = 0,
        limit: int = 100,
        *,
        role_set: set[str] | None = None,
    ) -> list[User]:
        """ADMIN/MODERATOR: all users. TENANT ADMIN: users in caller.tenant_id_cached only."""
        if caller.is_superuser:
            return await self._users.list_all(offset, limit)

        effective_role_set = role_set
        if effective_role_set is None:
            roles = await self._roles.get_user_roles(caller.id)
            effective_role_set = set(roles)

        if "ADMIN" in effective_role_set or "MODERATOR" in effective_role_set:
            return await self._users.list_all(offset, limit)
        if "TENANT ADMIN" in effective_role_set:
            tid = (caller.tenant_id_cached or "").strip()
            if not tid:
                raise AuthorizationError(
                    message="Your account has no tenant context; cannot list users.",
                    code="TENANT_CONTEXT_REQUIRED",
                )
            return await self._users.list_by_tenant(tid, offset, limit)
        # Fail-closed defense-in-depth: never silently return all users for unknown/unauthorized roles.
        raise AuthorizationError(
            message="You are not authorized to list users.",
            code="INSUFFICIENT_ROLE",
        )

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        return await self._users.get_by_id(user_id)

    async def get_user_by_id_for_caller(
        self,
        caller: User,
        user_id: int,
        *,
        role_set: set[str] | None = None,
    ) -> Optional[User]:
        """ADMIN/MODERATOR: any user. TENANT ADMIN: same tenant only."""
        user = await self._users.get_by_id(user_id)
        if not user:
            return None

        if caller.is_superuser:
            return user

        effective_role_set = role_set
        if effective_role_set is None:
            roles = await self._roles.get_user_roles(caller.id)
            effective_role_set = set(roles)

        if "ADMIN" in effective_role_set or "MODERATOR" in effective_role_set:
            return user
        if "TENANT ADMIN" in effective_role_set:
            tid = (caller.tenant_id_cached or "").strip()
            if not tid:
                raise AuthorizationError(
                    message="Your account has no tenant context; cannot view users.",
                    code="TENANT_CONTEXT_REQUIRED",
                )
            # Tenant isolation for TENANT ADMIN is enforced in the route layer
            # via `enforce_target_user_same_tenant`; here we only keep fail-closed role checks.
            return user
        # Fail-closed defense-in-depth: never silently return the target user for unknown/unauthorized roles.
        raise AuthorizationError(
            message="You are not authorized to view this user.",
            code="INSUFFICIENT_ROLE",
        )

    async def get_user_permission_names(self, user_id: int) -> list[str]:
        """Get permission names for a user (via roles)."""
        return await self._roles.get_user_permission_names(user_id)

    async def set_selected_api_key(self, user: User, api_key_id: Optional[int]) -> None:
        """Set the user's selected API key."""
        await self._users.update(user, {"selected_api_key_id": api_key_id})
        await self._users.commit()
