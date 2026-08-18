"""User CRUD business logic."""

from typing import Optional
from uuid import UUID

from app.core.exceptions import AuthorizationError
from app.core.constants import RoleName
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.utils.masking import drop_masked_pii, mask_email, mask_phone


class UserService:
    def __init__(self, user_repo: UserRepository, role_repo: RoleRepository) -> None:
        self._users = user_repo
        self._roles = role_repo

    async def get_user_profile(self, user: User) -> dict:
        roles = await self._roles.get_user_roles(user.id)
        return {
            "user_id": str(user.id),
            # PII masked for the response; never expose the decrypted value.
            "email": mask_email(user.email),
            "username": user.username,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_tenant_active": user.is_tenant_active,
            "creation_type": user.creation_type.value if user.creation_type else None,
            # Stringify tenant_id so it's consistent with user_id (also a string)
            # and the JWT tenant_id claim (also a string). Frontends call
            # .trim()/.includes() on these values.
            "tenant_id": str(user.tenant_id) if user.tenant_id is not None else None,
            "last_login": user.last_login,
            "avatar_url": user.avatar_url,
            "phone_number": mask_phone(user.phone_number),
            "timezone": user.timezone,
            "roles": roles,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    async def update_profile(self, user: User, data: dict) -> User:
        """Apply a partial update. Callers must validate `data` keys at the route layer
        (route Pydantic schema); the repo silently drops unknown keys.

        Responses return masked PII, so a client may echo a masked value back
        on save. Drop only masked email/phone fields to avoid overwriting the
        stored plaintext, while leaving other fields (which may legitimately
        contain ``*``) untouched.
        """
        data = drop_masked_pii(data)
        await self._users.update(user, data)
        await self._users.commit()
        return user

    async def _resolve_caller_role_set(
        self, caller: User, role_set: set[str] | None
    ) -> set[str]:
        if role_set is not None:
            return role_set
        roles = await self._roles.get_user_roles(caller.id)
        return set(roles)

    def _assert_tenant_context(self, caller: User, action: str) -> None:
        if caller.tenant_id is None:
            raise AuthorizationError(
                message=f"Your account has no tenant context; cannot {action}.",
                code="TENANT_CONTEXT_REQUIRED",
            )

    async def list_users_for_caller(
        self,
        caller: User,
        offset: int = 0,
        limit: int = 100,
        *,
        role_set: set[str] | None = None,
    ) -> list[User]:
        """ADMIN/MODERATOR see all users; TENANT ADMIN sees only their own tenant."""
        effective_role_set = await self._resolve_caller_role_set(caller, role_set)

        if RoleName.ADMIN.value in effective_role_set or RoleName.MODERATOR.value in effective_role_set:
            return await self._users.list_all(offset, limit)
        if RoleName.TENANT_ADMIN.value in effective_role_set:
            self._assert_tenant_context(caller, "list users")
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

        effective_role_set = await self._resolve_caller_role_set(caller, role_set)

        if RoleName.ADMIN.value in effective_role_set:
            return user
        if RoleName.TENANT_ADMIN.value in effective_role_set:
            self._assert_tenant_context(caller, "view users")
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
