"""User CRUD business logic."""

from typing import Optional
from uuid import UUID

from app.core.exceptions import AuthorizationError
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository


class UserService:
    def __init__(self, user_repo: UserRepository, role_repo: RoleRepository) -> None:
        self._users = user_repo
        self._roles = role_repo

    async def get_user_profile(self, user: User) -> dict:
        roles = await self._roles.get_user_roles(user.user_id)
        return {
            "user_id": str(user.user_id),
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_tenant_active": user.is_tenant_active,
            "creation_type": user.creation_type.value if user.creation_type else None,
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
            "last_login": user.last_login,
            "avatar_url": user.avatar_url,
            "phone_number": user.phone_number,
            "timezone": user.timezone,
            "roles": roles,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    async def update_profile(self, user: User, data: dict) -> User:
        """Apply a partial update. Callers must validate `data` keys at the route layer
        (route Pydantic schema); the repo silently drops unknown keys."""
        await self._users.update(user, data)
        await self._users.commit()
        return user

    async def list_users_for_caller(
        self,
        caller: User,
        offset: int = 0,
        limit: int = 100,
        *,
        role_set: set[str] | None = None,
    ) -> list[User]:
        """ADMIN/MODERATOR see all users; TENANT ADMIN sees only their own tenant."""
        effective_role_set = role_set
        if effective_role_set is None:
            roles = await self._roles.get_user_roles(caller.user_id)
            effective_role_set = set(roles)

        if "ADMIN" in effective_role_set or "MODERATOR" in effective_role_set:
            return await self._users.list_all(offset, limit)
        if "TENANT ADMIN" in effective_role_set:
            if caller.tenant_id is None:
                raise AuthorizationError(
                    message="Your account has no tenant context; cannot list users.",
                    code="TENANT_CONTEXT_REQUIRED",
                )
            return await self._users.list_by_tenant(caller.tenant_id, offset, limit)
        raise AuthorizationError(
            message="You are not authorized to list users.",
            code="INSUFFICIENT_ROLE",
        )

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        return await self._users.get_by_id(user_id)

    async def get_user_by_id_for_caller(
        self,
        caller: User,
        user_id: UUID,
        *,
        role_set: set[str] | None = None,
    ) -> Optional[User]:
        """ADMIN/MODERATOR can fetch any user; TENANT ADMIN can only fetch users
        in their own tenant (enforced both here and at the route layer via
        `enforce_target_user_same_tenant`)."""
        user = await self._users.get_by_id(user_id)
        if not user:
            return None

        effective_role_set = role_set
        if effective_role_set is None:
            roles = await self._roles.get_user_roles(caller.user_id)
            effective_role_set = set(roles)

        if "ADMIN" in effective_role_set or "MODERATOR" in effective_role_set:
            return user
        if "TENANT ADMIN" in effective_role_set:
            if caller.tenant_id is None:
                raise AuthorizationError(
                    message="Your account has no tenant context; cannot view users.",
                    code="TENANT_CONTEXT_REQUIRED",
                )
            if user.tenant_id != caller.tenant_id:
                raise AuthorizationError(
                    message="Cannot view a user outside your tenant.",
                    code="TENANT_FORBIDDEN",
                )
            return user
        raise AuthorizationError(
            message="You are not authorized to view this user.",
            code="INSUFFICIENT_ROLE",
        )
