"""
Tenant business logic — owns all tenant + tenant-user operations.

Routes are thin pass-throughs: they extract the current user, delegate here,
then shape the ORM result through a Pydantic schema. All scope enforcement,
repository access and AuthService coordination lives in this file.
"""

import logging
import re
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, status

from app.core.exceptions import EntityNotFoundError
from app.models.role_name import RoleName
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.schemas.tenant import (
    TenantCreate,
    TenantStatusUpdate,
    TenantUpdate,
    TenantUserCreate,
    TenantUserStatusUpdate,
    TenantUserUpdate,
)
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class TenantService:
    """All tenant + tenant-user operations. Routes never touch repos directly."""

    def __init__(
        self,
        tenant_repo: TenantRepository,
        user_repo: UserRepository,
        role_repo: RoleRepository,
        auth_service: AuthService,
    ) -> None:
        self._tenants = tenant_repo
        self._users = user_repo
        self._roles = role_repo
        self._auth = auth_service

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def derive_username_from_email(email: str) -> str:
        """Build a default username from the email's local part.

        Used when auto-provisioning a tenant admin from the contact email.
        Replaces non [a-zA-Z0-9_] chars with underscores; pads to ≥3 chars.
        """
        local = email.split("@", 1)[0]
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", local).strip("_") or "user"
        if len(sanitized) < 3:
            sanitized = (sanitized + "_user")[:100]
        return sanitized[:100]

    async def is_system_admin(self, user: User) -> bool:
        roles = await self._roles.get_user_roles(user.id)
        return RoleName.ADMIN.value in roles or RoleName.MODERATOR.value in roles

    async def enforce_scope(self, user: User, target_tenant_id: int) -> None:
        """Allow system admins; otherwise tenant must equal caller's tenant."""
        if await self.is_system_admin(user):
            return
        if user.tenant_id is None or user.tenant_id != target_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "TENANT_FORBIDDEN",
                    "message": "Cannot access a tenant you do not belong to.",
                },
            )

    async def _load_tenant_or_404(self, tenant_id: int) -> Tenant:
        tenant = await self._tenants.get_by_id(tenant_id)
        if not tenant:
            raise EntityNotFoundError(f"Tenant {tenant_id}")
        return tenant

    async def _load_tenant_user_or_404(self, tenant_id: int, user_id: UUID) -> User:
        target = await self._users.get_by_id(user_id)
        if not target:
            raise EntityNotFoundError(f"User {user_id}")
        if target.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "USER_NOT_IN_TENANT", "message": "User does not belong to this tenant."},
            )
        return target

    # ── Tenant CRUD ──────────────────────────────────────────────────────

    async def create_tenant(
        self,
        body: TenantCreate,
        current_user: User,
        background_tasks: BackgroundTasks,
    ) -> Tenant:
        """Create a tenant and auto-provision its first admin user.

        Atomic: tenant + user + verification token share the same DB session,
        so if user provisioning fails (duplicate email/username) the tenant
        insert is also rolled back.

        Side effect: a setup-link email is enqueued to the contact email.
        """
        if await self._tenants.get_by_email(body.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "DUPLICATE_TENANT_EMAIL", "message": "A tenant with this email already exists."},
            )

        tenant = Tenant(
            name=body.contact_name,
            organisation=body.organisation,
            email=body.email,
            phone_number=body.phone_number,
            status=TenantStatus.ACTIVATED,
            created_by=current_user.id,
        )
        await self._tenants.create(tenant)  # flush only — tenant_id now populated

        # Auto-provision the first admin user for this tenant. Username derives
        # from the email local part; on collision DuplicateEntityError rolls
        # the whole transaction back.
        await self._auth.provision_user(
            email=body.email,
            username=self.derive_username_from_email(body.email),
            full_name=body.contact_name,
            phone_number=body.phone_number,
            tenant_id=str(tenant.id),
            creation_type="tenant",
            role_name=RoleName.TENANT_ADMIN,
            background_tasks=background_tasks,
        )

        # provision_user committed; refresh to surface server-side defaults.
        await self._tenants.refresh(tenant)
        return tenant

    async def list_tenants(
        self,
        current_user: User,
        offset: int,
        limit: int,
        status_filter: Optional[TenantStatus],
    ) -> list[Tenant]:
        if await self.is_system_admin(current_user):
            return await self._tenants.list_all(offset=offset, limit=limit, status=status_filter)
        if current_user.tenant_id is None:
            return []
        own = await self._tenants.get_by_id(current_user.tenant_id)
        if own and (status_filter is None or own.status == status_filter):
            return [own]
        return []

    async def get_tenant(self, current_user: User, tenant_id: int) -> Tenant:
        await self.enforce_scope(current_user, tenant_id)
        return await self._load_tenant_or_404(tenant_id)

    async def update_tenant(
        self, current_user: User, tenant_id: int, body: TenantUpdate
    ) -> Tenant:
        tenant = await self._load_tenant_or_404(tenant_id)
        data = body.model_dump(exclude_unset=True)
        # Status changes go through PATCH /status to keep authorization split clean.
        data.pop("status", None)
        # Schema uses `contact_name` (frontend-aligned); model column is `name`.
        if "contact_name" in data:
            data["name"] = data.pop("contact_name")
        data["updated_by"] = current_user.id
        await self._tenants.update(tenant, data)
        await self._tenants.save_and_refresh(tenant)
        return tenant

    async def update_tenant_status(
        self, current_user: User, tenant_id: int, body: TenantStatusUpdate
    ) -> Tenant:
        tenant = await self._load_tenant_or_404(tenant_id)
        await self._tenants.update(
            tenant, {"status": body.status, "updated_by": current_user.id}
        )
        await self._tenants.save_and_refresh(tenant)
        return tenant

    # ── Tenant-user CRUD ─────────────────────────────────────────────────

    async def list_tenant_users(
        self, current_user: User, tenant_id: int, offset: int, limit: int
    ) -> list[User]:
        await self.enforce_scope(current_user, tenant_id)
        return await self._users.list_by_tenant(tenant_id, offset=offset, limit=limit)

    async def create_tenant_user(
        self,
        current_user: User,
        tenant_id: int,
        body: TenantUserCreate,
        background_tasks: BackgroundTasks,
    ) -> tuple[str, str]:
        """Provision an inactive user for the tenant. Returns (user_id, setup_token)."""
        await self.enforce_scope(current_user, tenant_id)
        if not await self._tenants.get_by_id(tenant_id):
            raise EntityNotFoundError(f"Tenant {tenant_id}")
        return await self._auth.provision_user(
            email=body.email,
            username=body.username,
            full_name=body.full_name,
            phone_number=body.phone_number,
            tenant_id=str(tenant_id),
            creation_type="tenant",
            background_tasks=background_tasks,
        )

    async def update_tenant_user(
        self,
        current_user: User,
        tenant_id: int,
        user_id: UUID,
        body: TenantUserUpdate,
    ) -> User:
        await self.enforce_scope(current_user, tenant_id)
        target = await self._load_tenant_user_or_404(tenant_id, user_id)
        payload = body.model_dump(exclude_unset=True)
        payload["updated_by"] = current_user.id
        await self._users.update(target, payload)
        await self._users.save_and_refresh(target)
        return target

    async def update_tenant_user_status(
        self,
        current_user: User,
        tenant_id: int,
        user_id: UUID,
        body: TenantUserStatusUpdate,
    ) -> User:
        await self.enforce_scope(current_user, tenant_id)
        target = await self._load_tenant_user_or_404(tenant_id, user_id)
        payload = body.model_dump(exclude_unset=True)
        payload["updated_by"] = current_user.id
        await self._users.update(target, payload)
        await self._users.save_and_refresh(target)
        return target

    async def delete_tenant_user(
        self, current_user: User, tenant_id: int, user_id: UUID
    ) -> None:
        await self.enforce_scope(current_user, tenant_id)
        target = await self._load_tenant_user_or_404(tenant_id, user_id)
        await self._users.update(
            target,
            {
                "is_delete": True,
                "is_active": False,
                "is_tenant_active": False,
                "updated_by": current_user.id,
            },
        )
        await self._users.commit()
