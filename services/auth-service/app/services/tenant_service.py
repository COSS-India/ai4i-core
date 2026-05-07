"""
Tenant business logic — owns all tenant + tenant-user operations.

Routes are thin pass-throughs: they extract the current user, delegate here,
then shape the ORM result through a Pydantic schema. All scope enforcement,
repository access and provisioning lives in this file.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from uuid import UUID

from ai4icore_email import EmailClient, EmailMessage
from fastapi import BackgroundTasks, HTTPException, status

from app.core.config import settings
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
from app.services.auth_email_templates import render_setup_link
from app.services.role_service import RoleService
from app.services.token_service import TokenService

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

    def _enqueue_email(
        self,
        background_tasks: Optional[BackgroundTasks],
        factory: Callable[[], EmailMessage],
    ) -> None:
        """Render and enqueue a send_safe call.

        ``factory`` is a zero-arg callable that returns an EmailMessage. Render
        is wrapped in try/except so a template/URL bug never 5xx's a request
        whose DB commit already succeeded — orphan-row prevention. Render
        failures are logged at ERROR for ops to catch via metrics.

        Silent no-op when no BackgroundTasks available (e.g. tests calling the
        service directly without a request).
        """
        if background_tasks is None:
            return
        try:
            message = factory()
        except Exception as exc:
            logger.error(
                "email render failed: error=%s",
                exc.__class__.__name__,
            )
            return
        background_tasks.add_task(self._email.send_safe, message)

    def _setup_token_expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=settings.setup_token_expire_hours)

    async def _resolve_tenant_id(self, explicit: Optional[int | str]) -> Optional[int]:
        """Honor an explicit tenant_id, otherwise fall back to the default tenant."""
        if explicit is not None:
            try:
                return int(explicit)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    message="Invalid tenant_id.",
                    code="INVALID_TENANT_ID",
                    errors=[f"tenant_id must be an integer, got: {explicit!r}"],
                ) from exc
        default = await self._tenants.get_by_organisation(settings.default_tenant_org)
        if default is None:
            logger.warning(
                "Default tenant '%s' not found; user will be created without a tenant_id.",
                settings.default_tenant_org,
            )
            return None
        return default.id

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
    ) -> tuple[str, str]:
        """Create an inactive user without credentials and generate a setup token.
        Returns (user_id_str, setup_token).

        ``role_name`` decides which role is assigned. Default ``RoleName.USER``
        for regular tenant members; pass ``RoleName.TENANT_ADMIN`` when
        provisioning the first admin user of a new tenant.
        """
        if await self._users.get_by_email(email):
            raise DuplicateEntityError("User", "email")
        if await self._users.get_by_username(username):
            raise DuplicateEntityError("User", "username")

        parsed_tenant_id = await self._resolve_tenant_id(tenant_id)
        creation = CreationType(creation_type) if creation_type in CreationType._value2member_map_ else CreationType.DEFAULT

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
        setup_token = self._tokens.create_setup_token(
            user_id=user_id_str,
            email=email,
            expires_delta=timedelta(hours=settings.setup_token_expire_hours),
        )

        token_obj = TokenVerification(
            token=setup_token,
            is_active=True,
            expires_at=self._setup_token_expires_at(),
            created_by=user.id,
        )
        await self._verifications.create(token_obj)
        await self._users.commit()

        logger.info("User provisioned (no credentials): %s (id=%s)", email, user.id)
        self._enqueue_email(background_tasks, lambda: render_setup_link(user, setup_token))
        return user_id_str, setup_token

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
        await self.provision_user(
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
        return await self.provision_user(
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
