"""
Tenant business logic — owns all tenant + tenant-user operations.

Routes are thin pass-throughs: they extract the current user, delegate here,
then shape the ORM result through a Pydantic schema. All scope enforcement,
repository access and provisioning lives in this file.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal, Optional
from uuid import UUID

from ai4icore_core.email import EmailClient, EmailMessage
from fastapi import BackgroundTasks, HTTPException, status

from app.core.config import settings
from app.core.constants import USERNAME_MAX_LENGTH
from app.core.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    ValidationError,
)
from app.models.role_name import RoleName
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, CreationType
from app.models.verification import TokenVerification
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_repository import VerificationRepository
from app.schemas.tenant import (
    TenantCreate,
    TenantStatusUpdate,
    TenantUpdate,
    TenantUserCreate,
    TenantUserStatusUpdate,
    TenantUserUpdate,
)
from app.services.auth_email_templates import render_setup_link, render_verify_email
from app.services.email_helpers import enqueue_email, persist_token_verification, resolve_tenant_id, setup_token_expires_at
from app.services.role_service import RoleService
from app.services.token_service import TokenService
from app.utils.username import allocate_unique_username, derive_username_from_email

logger = logging.getLogger(__name__)


class TenantService:
    """All tenant + tenant-user operations. Routes never touch repos directly."""

    def __init__(
        self,
        tenant_repo: TenantRepository,
        user_repo: UserRepository,
        role_service: RoleService,
        verification_repo: VerificationRepository,
        token_service: TokenService,
        email_client: EmailClient,
    ) -> None:
        self._tenants = tenant_repo
        self._users = user_repo
        self._roles = role_service
        self._verifications = verification_repo
        self._tokens = token_service
        self._email = email_client

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_username_segment(value: str) -> str:
        """Keep only [a-zA-Z0-9_]; collapse to a single underscore-separated segment."""
        return re.sub(r"[^a-zA-Z0-9_]", "_", (value or "").strip()).strip("_") or "user"

    @classmethod
    def derive_tenant_admin_username(cls, email: str, organisation: str) -> str:
        """Build a tenant-admin username from email local part + organisation.

        Same person at different orgs (e.g. name@tarento.com vs name@irctc.com)
        gets distinct usernames: ``ambarish_ganguly_tarento`` vs ``ambarish_ganguly_irctc``.
        """
        local = cls._sanitize_username_segment(email.split("@", 1)[0])
        org = cls._sanitize_username_segment(organisation)
        if len(local) < 3:
            local = f"{local}_user"[:50]
        base = f"{local}_{org}"
        if len(base) < 3:
            base = "tenant_admin"
        return base[:USERNAME_MAX_LENGTH]

    async def _allocate_unique_username(self, base: str) -> str:
        """Return ``base`` or ``base_2``, ``base_3`` if the username is taken."""
        return await allocate_unique_username(
            self._users.list_usernames_in_collision_family, base
        )

    async def is_system_admin(self, user: User) -> bool:
        roles = await self._roles.get_user_roles(user.id)
        return RoleName.ADMIN.value in roles or RoleName.MODERATOR.value in roles

    async def provision_user(
        self,
        email: str,
        username: str,
        full_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        tenant_id: Optional[int | str] = None,
        creation_type: str = "default",
        role_name: str = RoleName.USER,
        background_tasks: Optional[BackgroundTasks] = None,
        email_kind: Literal["setup", "verify", "none"] = "setup",
    ) -> tuple[str, str]:
        """Create an inactive user without credentials.

        Returns (user_id_str, token) where token is a setup or verify JWT.

        ``email_kind`` selects the onboarding email:
        - ``setup``: welcome + set-password link (new tenant admins and invited users)
        - ``verify``: verify-email link (/auth/register self-signup only)
        - ``none``: no email
        """
        if await self._users.get_by_email(email):
            raise DuplicateEntityError("User", "email")
        if await self._users.get_by_username(username):
            raise DuplicateEntityError("User", "username")

        parsed_tenant_id = await resolve_tenant_id(tenant_id, self._tenants)
        try:
            creation = CreationType(creation_type)
        except ValueError:
            creation = CreationType.DEFAULT

        user = User(
            email=email,
            username=username,
            full_name=full_name,
            phone_number=phone_number,
            tenant_id=parsed_tenant_id,
            is_active=False,
            creation_type=creation,
        )
        await self._users.create(user)

        try:
            await self._roles.assign_role(user.id, role_name)
        except EntityNotFoundError:
            logger.warning("Role %r not found, skipping role assignment.", role_name)

        user_id_str = str(user.id)
        expires_at = setup_token_expires_at()

        if email_kind == "verify":
            token = self._tokens.create_verify_token(user_id=user_id_str, email=email)
            await persist_token_verification(
                self._verifications, token, user.id, expires_at
            )
            await self._users.commit()
            logger.info("User provisioned (verify email): %s (id=%s)", email, user.id)
            enqueue_email(
                background_tasks,
                self._email,
                lambda: render_verify_email(user, token),
            )
            return user_id_str, token

        token = self._tokens.create_setup_token(user_id=user_id_str, email=email)
        await persist_token_verification(
            self._verifications, token, user.id, expires_at
        )
        await self._users.commit()

        logger.info("User provisioned (no credentials): %s (id=%s)", email, user.id)
        if email_kind == "setup":
            enqueue_email(
                background_tasks,
                self._email,
                lambda: render_setup_link(user, token),
            )
        return user_id_str, token

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

        Tenant starts PENDING. The contact admin receives one welcome/set-password email.
        Tenant becomes ACTIVE only after they set a password (see AuthService.set_password_with_token).
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
            status=TenantStatus.PENDING,
            created_by=current_user.id,
        )
        await self._tenants.create(tenant)  # flush only — tenant_id now populated

        admin_username = await self._allocate_unique_username(
            self.derive_tenant_admin_username(body.email, body.organisation)
        )
        await self.provision_user(
            email=body.email,
            username=admin_username,
            full_name=body.contact_name,
            phone_number=body.phone_number,
            tenant_id=str(tenant.id),
            creation_type="tenant",
            role_name=RoleName.TENANT_ADMIN,
            background_tasks=background_tasks,
            email_kind="setup",
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
        self,
        current_user: User,
        tenant_id: int,
        body: TenantStatusUpdate,
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
        email = body.email.lower().strip()
        username = await allocate_unique_username(
            self._users.list_usernames_in_collision_family,
            derive_username_from_email(email),
        )
        return await self.provision_user(
            email=email,
            username=username,
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
