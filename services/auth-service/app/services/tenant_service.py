"""
Tenant business logic — owns all tenant + tenant-user operations.

Routes are thin pass-throughs: they extract the current user, delegate here,
then shape the ORM result through a Pydantic schema. All scope enforcement,
repository access and provisioning lives in this file.
"""


import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, Literal, Optional
from uuid import UUID

import httpx

from ai4i_core.email import EmailClient, EmailMessage
from fastapi import BackgroundTasks, HTTPException, status

from app.core.config import settings
from app.core.constants import USERNAME_MAX_LENGTH
from app.core.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    ValidationError,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RoleName
from app.utils.common import role_name_to_str
from app.models.tenant import Tenant, TenantStatus
from app.models.tenant_plan import TenantPlan
from app.models.user import User, CreationType
from app.models.verification import TokenVerification
from app.repositories.credentials_repository import CredentialsRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_repository import VerificationRepository
from app.core.responses import to_response
from app.schemas.tenant import (
    TenantCreate,
    TenantResponse,
    TenantStatusUpdate,
    TenantUpdate,
    TenantUserCreate,
    TenantUserResponse,
    TenantUserRole,
    TenantUserStatusUpdate,
    TenantUserUpdate,
)
from app.schemas.user import UserListResponse
from app.services.api_key_service import APIKeyService
from app.services.auth_email_templates import render_account_deleted, render_setup_link, render_verify_email
from app.services.tenant_lifecycle import (
    TENANT_ONBOARDING_STATUSES,
    assert_default_tenant_not_targeted,
    assert_valid_tenant_status_transition,
    sync_tenant_users_for_status,
)
from app.services.email_helpers import (
    enqueue_email,
    persist_token_verification,
    reissue_setup_token,
    resolve_tenant_id,
    setup_token_expires_at,
)
from app.services.budget_usage import fetch_budget_usage
from app.services.role_service import RoleService
from app.services.tenant_name_cache import tenant_name_cache
from app.services.token_service import TokenService
from app.utils.masking import drop_masked_pii, mask_pii_in_dict
from app.utils.username import allocate_unique_username, derive_username_from_email

logger = logging.getLogger(__name__)

# Derived from tenants.allocated_budget's own column type (NUMERIC(15, 2))
# rather than hand-computed, so widening that column can't silently leave
# this stale — a stale literal here would keep rejecting valid budgets with
# a confident-sounding "exceeds the maximum allowed" instead of the column
# actually being able to hold them.
_allocated_budget_type = Tenant.__table__.c.allocated_budget.type
MAX_TENANT_BUDGET = Decimal(10) ** (
    _allocated_budget_type.precision - _allocated_budget_type.scale
) - Decimal(1).scaleb(-_allocated_budget_type.scale)


async def _assign_plan_to_tenant(tenant_id: int, plan_id: UUID, db: AsyncSession) -> None:
    base = (settings.platform_core_url or "").rstrip("/")
    if not base:
        logger.warning("platform_core_url not set; skipping plan assignment for tenant %s", tenant_id)
        return
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            plan_r = await client.get(f"{base}/api/v1/billing/policies/{plan_id}")
            svc_r = await client.get(f"{base}/api/v1/billing/policies/{plan_id}/services")
        if plan_r.status_code != 200:
            logger.error("platform-core GET policies/%s failed: %s %s", plan_id, plan_r.status_code, plan_r.text)
            return
        plan_data: Dict[str, Any] = plan_r.json()
        allowed_services = svc_r.json() if svc_r.status_code == 200 else []
    except Exception as e:
        logger.exception("_assign_plan_to_tenant HTTP error for tenant %s: %s", tenant_id, e)
        return

    try:
        cost = plan_data.get("cost")
        row = TenantPlan(
            tenant_id=tenant_id,
            plan_id=plan_id,
            plan_name=str(plan_data.get("plan_name") or ""),
            tier=str(plan_data.get("tier") or ""),
            plan_cost=Decimal(str(cost)) if cost is not None else None,
            quota_config=plan_data.get("quota_config") or {},
            rate_limit_config=plan_data.get("rate_limit_config") or {},
            allowed_services=allowed_services if isinstance(allowed_services, list) else [],
        )
        db.add(row)
        await db.commit()
        logger.info("TenantPlan created for tenant_id=%s plan_id=%s", tenant_id, plan_id)
    except Exception as e:
        await db.rollback()
        logger.exception("TenantPlan DB insert failed for tenant %s: %s", tenant_id, e)


def _assert_tenant_active_for_user_deactivation(
    tenant: Tenant, payload: dict
) -> None:
    """Tenant admins may set ``is_active=False`` only while the tenant is ACTIVE."""
    if payload.get("is_active") is not False:
        return
    if tenant.status != TenantStatus.ACTIVE:
        raise ValidationError(
            message="Tenant users can only be suspended while the tenant is active.",
            code="TENANT_NOT_ACTIVE",
        )


class TenantService:
    """All tenant + tenant-user operations. Routes never touch repos directly."""

    def __init__(
        self,
        tenant_repo: TenantRepository,
        user_repo: UserRepository,
        role_service: RoleService,
        verification_repo: VerificationRepository,
        credentials_repo: CredentialsRepository,
        token_service: TokenService,
        email_client: EmailClient,
        api_key_service: Optional[APIKeyService] = None,
        refresh_token_repo: Optional[RefreshTokenRepository] = None,
    ) -> None:
        self._tenants = tenant_repo
        self._users = user_repo
        self._roles = role_service
        self._verifications = verification_repo
        self._credentials = credentials_repo
        self._tokens = token_service
        self._email = email_client
        self._api_keys = api_key_service
        self._refresh_tokens = refresh_token_repo

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

    async def _deny_moderator(self, user: User) -> None:
        """Raise 403 if the caller is a Moderator. Use after enforce_scope on tenant-user operations."""
        roles = await self._roles.get_user_roles(user.id)
        if RoleName.MODERATOR.value in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "message": "Moderators cannot perform this action.",
                },
            )

    async def _assert_can_reveal_pii(self, user: User) -> None:
        """Gate unmasked-PII reads to the roles that can actually edit a tenant.

        Reading (masked) is available to anyone with tenant.read scope, but
        cleartext contact details are only needed by the Edit forms, which are
        limited to ADMIN and TENANT ADMIN. This excludes moderators and plain
        tenant users even when they hold read scope, so ``?unmask=true`` cannot
        be used to harvest cleartext PII. Callers must still pass
        ``enforce_scope`` first (a TENANT ADMIN is thereby limited to their own
        tenant; an ADMIN passes scope for any tenant).
        """
        roles = await self._roles.get_user_roles(user.id)
        if RoleName.ADMIN.value in roles or RoleName.TENANT_ADMIN.value in roles:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INSUFFICIENT_PERMISSIONS",
                "message": "You do not have permission to view unmasked contact details.",
            },
        )

    async def _assert_not_last_tenant_admin(self, target: User, tenant: Tenant) -> None:
        """Raise 422 if the target is the sole active TENANT ADMIN for their tenant.

        Prevents a tenant from becoming unmanageable by blocking deletion of
        the last admin. The check is on the target (not the caller) so it covers
        both self-deletion and an admin deleting another tenant admin.
        """
        roles = await self._roles.get_user_roles(target.id)
        if RoleName.TENANT_ADMIN.value not in roles:
            return
        # Serialize concurrent last-admin checks within the same tenant.
        await self._tenants._db.execute(
            text("SELECT pg_advisory_xact_lock(:tid)"), {"tid": tenant.id}
        )
        count = await self._roles.count_tenant_admins_in_tenant(tenant.id)
        if count <= 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "LAST_TENANT_ADMIN",
                    "message": (
                        f"Cannot delete user: {tenant.name} must retain at least one active Tenant Admin."
                    ),
                },
            )

    async def _set_tenant_user_role(
        self, user_id: UUID, role: TenantUserRole | RoleName | str, *, commit: bool = True
    ) -> None:
        target = role.value if isinstance(role, TenantUserRole) else role_name_to_str(role)
        await self._roles.assign_role(user_id, target, commit=commit)

    async def build_tenant_user_response(
        self, user: User, *, unmask_phone: bool = False
    ) -> dict:
        # Delegate to the batched builder so the payload shape is defined in
        # one place; the credentials/roles lookups handle a one-element list
        # at no extra cost.
        responses = await self.build_tenant_user_responses(
            [user], unmask_phone=unmask_phone
        )
        return responses[0]

    async def build_tenant_user_responses(
        self, users: list[User], *, unmask_phone: bool = False
    ) -> list[dict]:
        """Build list responses with a single batched role lookup.

        ``unmask_phone=True`` returns each user's phone number in cleartext so
        the Edit Tenant User form can pre-fill an editable value; the email is
        always masked (it is non-editable for tenant users).
        """
        if not users:
            return []
        user_ids = [u.id for u in users]
        roles_by_user = await self._roles.get_roles_for_users(user_ids)
        activated_ids = await self._credentials.user_ids_with_credentials(user_ids)
        responses: list[dict] = []
        for user in users:
            # role = self.resolve_tenant_user_role(roles_by_user.get(user.id, []))
            base = to_response(user, UserListResponse)
            responses.append(
                mask_pii_in_dict(
                    TenantUserResponse(
                        **base,
                        roles=roles_by_user.get(user.id, []),
                        is_tenant_active=user.is_tenant_active,
                        is_activated=user.id in activated_ids,
                    ).model_dump(mode="json", by_alias=True),
                    mask_phones=not unmask_phone,
                )
            )
        return responses

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
        if await self._users.email_exists(email):
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

    async def _load_tenant_for_update_or_404(self, tenant_id: int) -> Tenant:
        """Lock tenant row for the current transaction (see ``_require_tenant_active_for_user_creation``)."""
        tenant = await self._tenants.get_by_id_for_update(tenant_id)
        if not tenant:
            raise EntityNotFoundError(f"Tenant {tenant_id}")
        return tenant

    @staticmethod
    def _assert_tenant_active_for_user_creation(tenant: Tenant) -> None:
        if tenant.status != TenantStatus.ACTIVE:
            raise ValidationError(
                message="Tenant users can only be added when the tenant is active.",
                code="TENANT_NOT_ACTIVE",
            )

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
        platform_core_db: Optional[AsyncSession] = None,
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
        if await self._tenants.get_by_organisation(body.organisation):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "DUPLICATE_TENANT_ORGANISATION", "message": "A tenant with this organisation name already exists."},
            )
        if body.allocated_budget is not None and body.allocated_budget < 0:
            raise ValidationError(
                message="allocated_budget must not be negative.",
                code="INVALID_BUDGET",
            )
        if body.tier_id is not None:
            # Same lookup assign_tenant_tier uses — without it, a tenant
            # created with an unknown/inactive tier id would pass
            # create_api_key's NO_ACTIVE_TIER gate (which only checks
            # tenants.tier_id is non-null) and have that id baked into every
            # key's cache payload and emitted downstream as X-Tier-ID.
            if platform_core_db is None:
                raise ValidationError(
                    message="tier_id cannot be verified: platform-core DB is not configured.",
                    code="PLATFORM_CORE_DB_NOT_CONFIGURED",
                )
            tier_row = (
                await platform_core_db.execute(
                    text("SELECT id FROM tiers WHERE id = :tid AND is_active = true"),
                    {"tid": body.tier_id},
                )
            ).first()
            if tier_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "TIER_NOT_FOUND", "message": f"Tier '{body.tier_id}' not found."},
                )

        tenant = Tenant(
            name=body.contact_name,
            organisation=body.organisation,
            email=body.email,
            phone_number=body.phone_number,
            status=TenantStatus.PENDING,
            created_by=current_user.id,
            tier_id=body.tier_id,
            allocated_budget=body.allocated_budget,
            budget_effective_from=body.budget_effective_from,
            budget_effective_to=body.budget_effective_to,
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
        tenant_name_cache.set_name(tenant.id, tenant.organisation)

        if body.plan_id:
            try:
                await _assign_plan_to_tenant(tenant.id, body.plan_id, self._tenants._db)
            except Exception as e:
                logger.exception("Plan assignment after tenant creation failed (tenant was created): %s", e)

        return tenant

    async def list_tenants(
        self,
        current_user: User,
        offset: int,
        limit: int,
        status_filter: Optional[TenantStatus],
        *,
        is_admin: bool = False,
    ) -> list[Tenant]:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "message": "Only administrators can list all tenants.",
                },
            )
        return await self._tenants.list_all(offset=offset, limit=limit, status=status_filter)

    async def get_tenant(
        self, current_user: User, tenant_id: int, *, unmask: bool = False, is_admin: bool = False
    ) -> Tenant:
        if not is_admin:
            await self.enforce_scope(current_user, tenant_id)
        if unmask:
            await self._assert_can_reveal_pii(current_user)
        return await self._load_tenant_or_404(tenant_id)

    @staticmethod
    def build_tenant_response(tenant: Tenant, *, unmask: bool = False) -> dict:
        """Shape a tenant into its API dict, applying the PII-masking policy.

        Default (list/view): email and phone are masked. With ``unmask`` (Edit
        Tenant form): the phone is always revealed and the contact email is
        revealed only while the tenant is PENDING — i.e. before verification,
        the only window in which the email may still be corrected.
        """
        data = to_response(tenant, TenantResponse)
        if unmask:
            return mask_pii_in_dict(
                data,
                mask_emails=tenant.status != TenantStatus.PENDING,
                mask_phones=False,
            )
        return mask_pii_in_dict(data)

    @staticmethod
    def _prepare_tenant_update_payload(body: TenantUpdate) -> dict:
        """Shape the incoming PATCH body into the tenant-column update dict.

        Drops a masked email/phone a client echoed back unchanged (responses
        return masked PII, so an unmodified value must never overwrite the
        stored plaintext), removes ``status`` (that goes through PATCH
        /status to keep authorization split clean), and renames the
        frontend-aligned ``contact_name`` to the model's ``name`` column.
        """
        data = body.model_dump(exclude_unset=True)
        data = drop_masked_pii(data)
        data.pop("status", None)
        if "contact_name" in data:
            data["name"] = data.pop("contact_name")
        return data

    async def _assert_organisation_available(self, data: dict, tenant_id: int) -> None:
        if "organisation" not in data:
            return
        existing = await self._tenants.get_by_organisation(data["organisation"])
        if existing and existing.id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "DUPLICATE_TENANT_ORGANISATION",
                    "message": "A tenant with this organisation name already exists.",
                },
            )

    async def _resolve_pending_email_admin(
        self, tenant: Tenant, data: dict
    ) -> tuple[str, str, Optional[User]]:
        """Determine whether this update is a PENDING-tenant email change and,
        if so, load + validate the admin user that must be re-aligned.

        Returns (old_email, new_email, admin) — admin is None unless this is
        a pending-tenant email change, in which case it's guaranteed non-None
        (a missing admin raises rather than returning None) so the caller can
        use ``admin is not None`` as the single signal for "reissue needed".
        """
        old_email = (tenant.email or "").lower().strip()
        new_email_raw = data.get("email")
        new_email = (new_email_raw or "").lower().strip() if new_email_raw else ""
        email_changed = bool(new_email) and new_email != old_email
        if not (email_changed and tenant.status == TenantStatus.PENDING):
            return old_email, new_email, None

        # Look up the admin user BEFORE the email-uniqueness check below, so
        # that check can be admin-aware (a user row whose id matches the
        # admin we're about to re-align is not a real collision).
        admin = await self._users.get_by_email(old_email)
        if admin is None or admin.tenant_id != tenant.id:
            # No admin to re-issue against → fail loudly. Otherwise the
            # tenant.email would change while the original activation link
            # (bound to whichever user actually exists) stays live, which
            # is the inconsistency this flow exists to prevent.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "TENANT_ADMIN_NOT_FOUND",
                    "message": (
                        "Cannot update tenant email: the tenant's admin "
                        "user could not be located, so the existing "
                        "activation link cannot be invalidated."
                    ),
                },
            )
        return old_email, new_email, admin

    async def _assert_email_available(
        self, data: dict, tenant_id: int, admin: Optional[User]
    ) -> None:
        """Single, admin-aware email-uniqueness check. Consolidates what
        PR #828 added (cross-tenant tenant+user collision) with the
        reissue-time check this PR needed (any non-admin user collision),
        so there is exactly one query per table and one place that owns
        email uniqueness for this endpoint.
        """
        if "email" not in data:
            return
        existing_tenant = await self._tenants.get_by_email(data["email"])
        if existing_tenant and existing_tenant.id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "DUPLICATE_TENANT_EMAIL",
                    "message": "A tenant with this email already exists.",
                },
            )
        existing_user = await self._users.get_by_email(data["email"])
        if existing_user is None:
            return
        if admin is not None:
            # Reissue flow will assign ``admin.email = new_email``. Any other
            # holder — same-tenant or cross-tenant — breaks the users.email
            # UNIQUE constraint at flush time, so only the admin themselves
            # is an allowed match.
            collides = existing_user.id != admin.id
        else:
            # No reissue planned: tenant.email is independent of users.email,
            # so a same-tenant user happening to share the address is
            # harmless. Only reject cross-tenant.
            collides = existing_user.tenant_id != tenant_id
        if collides:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "DUPLICATE_EMAIL",
                    "message": "This email is already in use.",
                },
            )

    async def update_tenant(
        self,
        current_user: User,
        tenant_id: int,
        body: TenantUpdate,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> Tenant:
        """Patch a tenant's editable fields.

        When the tenant is ``PENDING`` and the email changes, the
        auto-provisioned admin user's email is updated to match, their
        outstanding SETUP tokens are deactivated, and a fresh activation
        email is enqueued to the new address.

        Transactional contract: every write — tenant column update, admin's
        ``users.email``, token deactivation, new ``token_verification`` row
        — flushes against the SAME ``AsyncSession`` and is committed once
        at the end. Any pre-commit failure (409 on duplicate email, admin
        not found, helper raise) aborts the whole change. The activation
        email is enqueued **after** commit, so a rolled-back transaction
        can never leak a delivered email whose token no longer exists.
        """
        # TENANT ADMIN now holds tenant.update (perm 42), which the gateway
        # shares between this profile endpoint and the status endpoint. Without
        # a scope check a Tenant Admin could PATCH any tenant by id; restrict
        # non-admins to their own tenant (system admins pass through).
        await self.enforce_scope(current_user, tenant_id)
        tenant = await self._load_tenant_or_404(tenant_id)
        data = self._prepare_tenant_update_payload(body)
        if "organisation" in data and data["organisation"].strip().casefold() != tenant.organisation.strip().casefold():
            # The Default Organisation guards (status, TENANT ADMIN) key off
            # this name — renaming it would silently disable all of them.
            # Compare against the stored value (not just presence) so the
            # Edit Tenant form, which always echoes organisation back, can
            # still save unrelated field changes.
            assert_default_tenant_not_targeted(
                tenant,
                message="The Default Organisation cannot be renamed.",
            )

        # ── Pre-validation. Every failure-prone check runs BEFORE any write,
        # so the tenant.email change is never committed without the matching
        # admin-email update + token invalidation.
        await self._assert_organisation_available(data, tenant_id)
        old_email, new_email, admin = await self._resolve_pending_email_admin(tenant, data)
        await self._assert_email_available(data, tenant_id, admin)

        # ── Stage writes against the open session (flush only, no commit).
        data["updated_by"] = current_user.id
        await self._tenants.update(tenant, data)

        new_setup_token: Optional[str] = None
        if admin is not None:
            # Aligns admin's email with the tenant's, then delegates the
            # SETUP-token deactivation + new token mint to the shared helper
            # (same path used by AuthService.resend_setup_link, so the
            # token-type scoping and credentials guard stay in lockstep).
            admin.email = new_email
            new_setup_token = await reissue_setup_token(
                admin,
                credentials_repo=self._credentials,
                verifications_repo=self._verifications,
                token_service=self._tokens,
                background_tasks=background_tasks,
            )

        # ── Single atomic commit + refresh.
        await self._tenants.commit()
        await self._tenants.refresh(tenant)
        if "organisation" in data:
            tenant_name_cache.set_name(tenant.id, tenant.organisation)

        # ── Email enqueue happens AFTER the commit so a rolled-back tx can't
        # leak a delivered email whose token row was never persisted.
        if admin is not None and new_setup_token is not None:
            logger.info(
                "Re-issued tenant activation link for tenant %s: %s → %s",
                tenant.id, old_email, new_email,
            )
            enqueue_email(
                background_tasks,
                self._email,
                lambda: render_setup_link(admin, new_setup_token),
            )
        return tenant

    async def update_tenant_status(
        self,
        current_user: User,
        tenant_id: int,
        body: TenantStatusUpdate,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> Tenant:
        roles = await self._roles.get_user_roles(current_user.id)
        if RoleName.ADMIN.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "message": "Only administrators can change tenant status.",
                },
            )
        tenant = await self._load_tenant_for_update_or_404(tenant_id)
        if body.status != TenantStatus.ACTIVE:
            assert_default_tenant_not_targeted(
                tenant,
                message="The Default Organisation cannot be suspended or deactivated.",
            )
        assert_valid_tenant_status_transition(tenant.status, body.status)
        await sync_tenant_users_for_status(
            self._users, tenant_id, body.status, updated_by=current_user.id
        )
        await self._tenants.update(
            tenant, {"status": body.status, "updated_by": current_user.id}
        )
        await self._tenants.save_and_refresh(tenant)
        if self._api_keys is not None:
            if body.status == TenantStatus.SUSPENDED:
                # Keep is_active=True (Inactive): same key auto-resumes on reactivation.
                await self._api_keys.evict_keys_for_tenant(tenant_id)
            elif body.status == TenantStatus.DEACTIVATED:
                # Permanent revoke (is_active=False): reactivation requires a new key.
                await self._api_keys.revoke_keys_for_tenant(tenant_id)
            elif body.status == TenantStatus.ACTIVE:
                # Repopulates Redis only for keys that are still is_active=True.
                await self._api_keys.refresh_keys_cache_for_tenant(tenant_id)
        return tenant

    async def get_tenant_plan(self, tenant_id: int) -> dict:
        result = await self._tenants._db.execute(
            select(TenantPlan, Tenant)
            .join(Tenant, Tenant.id == TenantPlan.tenant_id)
            .where(TenantPlan.tenant_id == tenant_id)
            .order_by(TenantPlan.assigned_at.desc())
            .limit(1)
        )
        row = result.first()
        if not row:
            raise EntityNotFoundError(f"Plan for tenant {tenant_id}")
        plan, tenant = row
        return {
            "tenant_id": str(tenant_id),
            "tenant_name": tenant.name,
            "plan_id": str(plan.plan_id),
            "plan_name": plan.plan_name,
            "tier": plan.tier,
            "plan_cost": float(plan.plan_cost) if plan.plan_cost is not None else None,
            "quota_config": plan.quota_config or {},
            "rate_limit_config": plan.rate_limit_config or {},
            "allowed_services": plan.allowed_services or [],
        }

    # ── Tenant tier / budget ─────────────────────────────────────────────
    # Replaces the old platform-core-service pay-per-use endpoints
    # (POST/PATCH /pay-per-use/tenant/tier[, /reassign], PATCH
    # /pay-per-use/tenant/budget): tier and budget now live directly on
    # tenants.tier_id / tenants.allocated_budget, so these operate on the
    # local Tenant row with no cross-DB PPU-assignment bookkeeping and no
    # HTTP round trip to another service.

    async def assign_tenant_tier(
        self,
        current_user: User,
        tenant_id: int,
        tier_id_str: str,
        platform_core_db: Optional[AsyncSession],
    ) -> Tenant:
        """Assign (or reassign) a tenant's tier — PATCH /auth/tenants/{id}/tier.

        Restricted to ADMIN: this changes what a tenant is billed against,
        the same trust level as PATCH /auth/tenants/{id}/budget.

        409 TENANT_ALREADY_ON_TIER is raised whenever tenants.tier_id already
        matches the requested tier. tenants.tier_id is now the SOLE source of
        truth for a tenant's active tier (create_api_key's NO_ACTIVE_TIER gate
        already reads only this column, not a separate assignment table) — so
        this is a single atomic write with no second table to fall out of
        sync with. Previously this also write-through'd to platform-core's
        ppu_tenant_tier_assignments (dropped by AI4IDS-2923; see
        _sync_ppu_wallet_and_exhaustion for the equivalent fix on the budget
        side) and had to distinguish a genuine no-op from a partial failure
        between the two writes — that whole class of problem no longer exists
        with only one write to make.
        """
        roles = await self._roles.get_user_roles(current_user.id)
        if RoleName.ADMIN.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "message": "Only administrators can assign a tenant's tier.",
                },
            )
        try:
            tier_uuid = UUID(tier_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_TIER_ID", "message": "tier_id must be a valid UUID."},
            )

        tenant = await self._load_tenant_for_update_or_404(tenant_id)

        if platform_core_db is None:
            raise ValidationError(
                message="Tier assignment cannot be verified: platform-core DB is not configured.",
                code="PLATFORM_CORE_DB_NOT_CONFIGURED",
            )
        row = (
            await platform_core_db.execute(
                text("SELECT id, name FROM tiers WHERE id = :tid AND is_active = true"),
                {"tid": tier_uuid},
            )
        ).first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "TIER_NOT_FOUND", "message": f"Tier '{tier_id_str}' not found."},
            )

        if tenant.tier_id == tier_uuid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "TENANT_ALREADY_ON_TIER",
                    "message": f"Tenant '{tenant_id}' is already on tier '{row.name}'.",
                },
            )
        await self._tenants.update(
            tenant, {"tier_id": tier_uuid, "updated_by": current_user.id}
        )
        await self._tenants.save_and_refresh(tenant)

        if self._api_keys is not None:
            # Quota is tier-scoped: flags earned under the old tier would
            # otherwise keep 429'ing requests under the new one until the
            # monthly cron. Cached tier_id also has to be force-written —
            # every other cache writer preserves the existing value instead
            # of recomputing it (see _preserved_tier_id), since a tier
            # reassignment is the one case that legitimately changes it for
            # already-issued keys.
            await self._api_keys.clear_quota_flags_for_tenant(tenant_id)
            await self._api_keys.set_tier_id_for_tenant(tenant_id, str(tier_uuid))
        return tenant

    async def _sync_ppu_wallet_and_exhaustion(
        self,
        tenant_id: int,
        allocated_budget: Decimal,
        platform_core_db: AsyncSession,
    ) -> None:
        """Recompute budget-exhausted from ``allocated_budget`` (the value
        the caller just committed to tenants.allocated_budget — passed
        explicitly rather than re-read off the tenant object, so this does
        not depend on the caller's update()/save_and_refresh() having
        mutated it in place) minus this tenant's total spend, and mirror the
        result onto this tenant's cached API keys — the write-through the
        old revise_budget endpoint did via its budget-exhausted webhook to
        auth-service. Without this, a top-up moves tenants.allocated_budget
        but a key already flagged budget-exhausted=1 from a prior top-down
        has no path back to 0.

        Asymmetric on purpose, NOT a blanket set-or-clear of every key:
          * Tenant pool genuinely depleted (exhausted=True) -> every key
            under the tenant really is out of budget now regardless of its
            own individual ceiling, so every one is flagged
            (set_budget_exhausted_for_tenant, unchanged from before).
          * Tenant pool has headroom again (exhausted=False) -> must NOT
            blindly clear every key. A key's own budget_usage.
            api_key_budget_snap/api_key_budget_used is an INDEPENDENT
            constraint from this tenant-aggregate one (see
            set_budget_exhausted_for_key) — clearing a key that's still
            individually over its own ceiling just because the tenant's
            total looks fine again would let it bill again with zero
            headroom of its own. Only keys that are ALSO not individually
            exhausted get cleared; an individually-exhausted key keeps its
            flag untouched by this path (it only clears via its own future
            reallocation, same as always).

        Previously read/wrote a dedicated wallet row on platform-core's
        ppu_tenant_tier_assignments (dropped by AI4IDS-2923). Reconstructed
        here the same way platform-core-service's own get_tenant_budgets was
        (see usage_repository.py): allocated_budget lives on tenants (this
        DB); spend lives in budget_usage (platform-core's DB), keyed by
        api_key_id — summed here across every api_key under this tenant's
        applications (this DB), not just active ones, since a revoked key's
        past spend still counts against the tenant's allocated_budget.

        Best-effort by design (unlike the tier write-through): the primary
        write — tenants.allocated_budget — has already committed by the time
        this runs, so a failure anywhere here (platform-core unreachable,
        cache write failure) degrades to a stale cached exhaustion flag
        rather than rolling back an otherwise-successful budget revision —
        hence the whole recompute-and-write, not just the fetch, sits inside
        one try/except.
        """
        if self._api_keys is None:
            return
        try:
            key_ids = await self._api_keys.list_key_ids_for_tenant(tenant_id)
            usage = await fetch_budget_usage(key_ids, platform_core_db, raise_on_error=True)
            total_spent = sum((used for used, _snap in usage.values()), Decimal("0"))
            exhausted = (allocated_budget - total_spent) <= 0

            if exhausted:
                await self._api_keys.set_budget_exhausted_for_tenant(tenant_id, True)
                return

            for key_id in key_ids:
                used, snap = usage.get(key_id, (Decimal("0"), None))
                individually_exhausted = snap is not None and used >= snap
                if not individually_exhausted:
                    await self._api_keys.set_budget_exhausted_for_key(key_id, False)
        except Exception:
            logger.exception(
                "Failed to recompute budget-exhausted state for tenant_id=%s "
                "after budget revision; tenants.allocated_budget was still updated.",
                tenant_id,
            )

    async def revise_tenant_budget(
        self,
        current_user: User,
        tenant_id: int,
        action: Literal["top-up", "top-down"],
        amount: Decimal,
        platform_core_db: Optional[AsyncSession] = None,
    ) -> Tenant:
        """Top-up or top-down a tenant's budget — PATCH /auth/tenants/{id}/budget.

        Restricted to ADMIN, same as assign_tenant_tier. Unlike the old
        platform-core endpoint this replaces, there is no available_balance
        (or any other spend-tracking figure) on ``tenants`` itself — spend
        lives in platform-core's budget_usage ledger, summed here across
        every API key under the tenant. budget/key allocation recompute
        (applications_recomputed/keys_recomputed on the response) is still
        out of scope — always None here.

        A top-down is REJECTED, not just flagged after the fact, when it
        would drop the budget below this tenant's total spend to date
        (409 budget_below_consumed — restores the check the old
        platform-core endpoint had, which this rebuild had dropped for lack
        of a spend figure to check against; see budget_usage). This needs
        platform_core_db to verify: a top-down is refused outright
        (503 spend_verification_unavailable) rather than allowed
        unverified, unlike _sync_ppu_wallet_and_exhaustion's own read below,
        which is best-effort because ITS write already happened by the time
        it runs — this check gates the write itself. No optimistic-locking
        (expected_version) either — deemed unnecessary for this release.

        Uses the error-body shape (``{"error": ..., "message": ...}``) the
        contract specifies for this endpoint specifically, matching the old
        endpoint it replaces — every other tenant endpoint in this file uses
        ``{"code": ..., "message": ...}``.

        ``platform_core_db`` also drives ``_sync_ppu_wallet_and_exhaustion``
        (best-effort, see its own docstring) to recompute and sync the
        cached budget-exhausted flag on this tenant's API keys after the
        revision commits.
        """
        roles = await self._roles.get_user_roles(current_user.id)
        if RoleName.ADMIN.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "message": "Only administrators can revise a tenant's budget.",
                },
            )

        tenant = await self._load_tenant_for_update_or_404(tenant_id)

        current_budget = tenant.allocated_budget or Decimal("0")
        delta = amount if action == "top-up" else -amount
        new_budget = current_budget + delta

        if action == "top-up" and new_budget > MAX_TENANT_BUDGET:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "budget_limit_exceeded",
                    "message": (
                        f"Top-up would raise the budget to {new_budget}, exceeding "
                        f"the maximum allowed ({MAX_TENANT_BUDGET})"
                    ),
                },
            )
        if action == "top-down" and new_budget < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "budget_negative",
                    "message": f"Top-down amount exceeds the current budget ({current_budget})",
                },
            )

        if action == "top-down":
            # Cheaper, purely-local checks (above) run first; only reach for
            # platform-core once a top-down has already passed those.
            if self._api_keys is None or platform_core_db is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "spend_verification_unavailable",
                        "message": "Cannot verify this tenant's current spend right now — "
                        "refusing an unverified top-down rather than risking pushing it "
                        "below what's already been spent.",
                    },
                )
            try:
                key_ids = await self._api_keys.list_key_ids_for_tenant(tenant_id)
                usage = await fetch_budget_usage(key_ids, platform_core_db, raise_on_error=True)
            except Exception:
                logger.exception(
                    "Failed to verify spend for tenant_id=%s ahead of a top-down; refusing it.",
                    tenant_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "spend_verification_unavailable",
                        "message": "Cannot verify this tenant's current spend right now — "
                        "refusing an unverified top-down rather than risking pushing it "
                        "below what's already been spent.",
                    },
                )
            total_spent = sum((used for used, _snap in usage.values()), Decimal("0"))
            if new_budget < total_spent:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "budget_below_consumed",
                        "message": (
                            f"Top-down would drop the budget to {new_budget}, below this "
                            f"tenant's total spend to date ({total_spent}) across its API keys."
                        ),
                    },
                )

        await self._tenants.update(
            tenant,
            {
                "allocated_budget": new_budget,
                "updated_by": current_user.id,
            },
        )
        await self._tenants.save_and_refresh(tenant)

        if platform_core_db is not None:
            await self._sync_ppu_wallet_and_exhaustion(tenant_id, new_budget, platform_core_db)
        return tenant

    async def list_tenant_tiers(
        self,
        current_user: User,
        tier_id: Optional[str],
        platform_core_db: Optional[AsyncSession],
    ) -> list[dict]:
        """GET /auth/tenants/tier/list. ADMIN-only, matching the old
        GET /pay-per-use/tenant/tier's permission id (145, ppu.tenant.read)
        — enforced in-code here too, not just via api_permissions.json,
        the same defense-in-depth pattern as assign_tenant_tier /
        revise_tenant_budget. tier_name is resolved from platform-core's
        ``tiers`` table (no cross-DB FK is possible), batched for the set
        of tier_ids actually in play — the same cross-DB pattern
        create_api_key uses for tier_id lookups."""
        roles = await self._roles.get_user_roles(current_user.id)
        if RoleName.ADMIN.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "message": "Only administrators can list tenant tier assignments.",
                },
            )
        # Fail closed on a missing platform-core connection, same as
        # assign_tenant_tier — previously this degraded silently instead:
        # tier_name came back null for every row with no log line, and the
        # tier_id filter's existence check was skipped outright, so
        # filtering by a nonexistent tier returned an empty list (200)
        # instead of 404. A misconfiguration should not present as "all
        # tiers happen to be unnamed" / "this tier happens to have no
        # tenants".
        if platform_core_db is None:
            raise ValidationError(
                message="Tier data cannot be resolved: platform-core DB is not configured.",
                code="PLATFORM_CORE_DB_NOT_CONFIGURED",
            )

        tier_uuid: Optional[UUID] = None
        if tier_id is not None:
            try:
                tier_uuid = UUID(tier_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "INVALID_TIER_ID", "message": "tier_id must be a valid UUID."},
                )
            # is_active = true, matching assign_tenant_tier's lookup — a tier
            # listable here but rejected as not-found on assign would be a
            # visible inconsistency between the two endpoints.
            exists = (
                await platform_core_db.execute(
                    text("SELECT 1 FROM tiers WHERE id = :tid AND is_active = true"), {"tid": tier_uuid}
                )
            ).first()
            if exists is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "TIER_NOT_FOUND", "message": f"Tier '{tier_id}' not found"},
                )

        tenants = await self._tenants.list_with_tier(tier_uuid)

        tier_names: dict[UUID, str] = {}
        if tenants:
            ids = list({t.tier_id for t in tenants})
            rows = (
                await platform_core_db.execute(
                    text("SELECT id, name FROM tiers WHERE id = ANY((:ids)::uuid[])"), {"ids": ids}
                )
            ).all()
            tier_names = {row.id: row.name for row in rows}

        return [
            {
                "tenant_id": t.id,
                "tenant_name": t.organisation,
                "tier_id": str(t.tier_id),
                "tier_name": tier_names.get(t.tier_id),
                "allocated_budget": t.allocated_budget,
                "budget_effective_from": t.budget_effective_from,
                "budget_effective_to": t.budget_effective_to,
                "updated_at": t.updated_at,
            }
            for t in tenants
        ]

    # ── Tenant-user CRUD ─────────────────────────────────────────────────

    async def list_tenant_users(
        self,
        current_user: User,
        tenant_id: int,
        offset: int,
        limit: int,
        *,
        unmask: bool = False,
    ) -> list[User]:
        await self.enforce_scope(current_user, tenant_id)
        await self._deny_moderator(current_user)
        # Cleartext phone numbers are only for the Edit Tenant User form, which
        # is limited to ADMIN / TENANT ADMIN (masked listing stays open).
        if unmask:
            await self._assert_can_reveal_pii(current_user)
        await self._load_tenant_or_404(tenant_id)
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
        await self._deny_moderator(current_user)
        # Lock tenant row until provision_user commits — prevents suspend/deactivate
        # between the ACTIVE check and user insert in the same request.
        tenant = await self._load_tenant_for_update_or_404(tenant_id)
        self._assert_tenant_active_for_user_creation(tenant)
        if body.role == TenantUserRole.TENANT_ADMIN:
            assert_default_tenant_not_targeted(tenant)
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
            role_name=body.role.value,
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
        await self._deny_moderator(current_user)
        tenant = await self._load_tenant_or_404(tenant_id)
        target = await self._load_tenant_user_or_404(tenant_id, user_id)
        payload = body.model_dump(exclude_unset=True)
        # Drop masked email/phone a client echoed back unchanged (responses are
        # masked); scoped to PII keys so other ``*``-bearing fields survive.
        payload = drop_masked_pii(payload)
        role_update = payload.pop("role", None)
        if role_update == TenantUserRole.TENANT_ADMIN.value:
            assert_default_tenant_not_targeted(tenant)
        payload["updated_by"] = current_user.id
        await self._users.update(target, payload)
        if role_update is not None:
            # Single commit via save_and_refresh — role repo shares this session.
            await self._set_tenant_user_role(target.id, role_update, commit=False)
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
        await self._deny_moderator(current_user)
        tenant = await self._load_tenant_or_404(tenant_id)
        target = await self._load_tenant_user_or_404(tenant_id, user_id)
        if body.is_active is False and target.id == current_user.id:
            caller_roles = await self._roles.get_user_roles(current_user.id)
            if RoleName.TENANT_ADMIN.value in caller_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "SELF_DEACTIVATION_FORBIDDEN",
                        "message": "Tenant admins cannot deactivate their own account.",
                    },
                )
        payload = {"is_active": body.is_active, "updated_by": current_user.id}
        _assert_tenant_active_for_user_deactivation(tenant, payload)

        await self._users.update(target, payload)
        await self._users.save_and_refresh(target)
        # No per-user API key cache refresh: keys belong to Applications, not
        # Users (migration e9f0a1b2c3d4) — one tenant user's status has no
        # bearing on any key's eligibility.
        return target

    async def resend_tenant_user_setup_link(
        self,
        current_user: User,
        tenant_id: int,
        user_id: UUID,
        background_tasks: BackgroundTasks,
    ) -> None:
        """Re-send the set-password (SETUP) email for a not-yet-activated tenant user.

        Tenant users are provisioned passwordless (``email_kind="setup"``), so
        the onboarding email is a set-password link — NOT an email-verification
        link. ``/auth/resend-verification`` therefore no-ops for them (it only
        serves self-registered users who already hold credentials). Resolving
        by ``user_id`` (already unmasked in the tenant-user list) avoids the
        masked-email / PENDING-tenant limits of ``/auth/resend-setup-link``,
        which only targets the tenant contact admin.
        """
        await self.enforce_scope(current_user, tenant_id)
        await self._deny_moderator(current_user)
        tenant = await self._load_tenant_or_404(tenant_id)
        # Match the window enforced at set-password time
        # (AuthService.assert_tenant_allows_onboarding). PENDING must stay
        # allowed: a PENDING tenant's contact admin is exactly the user who
        # needs a resend, and their set-password is what activates the tenant.
        # Only SUSPENDED/DEACTIVATED would produce a link that dies on click.
        if tenant.status not in TENANT_ONBOARDING_STATUSES:
            raise ValidationError(
                message="Setup links can only be resent while the tenant is pending or active.",
                code="TENANT_NOT_ACTIVE",
            )
        target = await self._load_tenant_user_or_404(tenant_id, user_id)
        # Per-user tenant lock, set either by the tenant status cascade or by
        # PATCH /tenants/{id}/users/{id}/status. set_password_with_token does
        # not check this flag, so the user could set a password and still be
        # refused at login — block the resend instead.
        if target.is_tenant_active is False:
            raise ValidationError(
                message="This user's access is suspended; reactivate before resending.",
                code="USER_SUSPENDED",
            )

        setup_token = await reissue_setup_token(
            target,
            credentials_repo=self._credentials,
            verifications_repo=self._verifications,
            token_service=self._tokens,
            background_tasks=background_tasks,
        )
        if setup_token is None:
            # reissue_setup_token returns None when the user already has
            # credentials (setup complete) — there is nothing to resend.
            raise ValidationError(
                message="This user has already set a password; no activation link is needed.",
                code="USER_ALREADY_ACTIVATED",
            )

        await self._users.commit()
        logger.info(
            "Set-password link resent for tenant user id=%s (tenant %s)",
            target.id,
            tenant_id,
        )
        enqueue_email(
            background_tasks,
            self._email,
            lambda: render_setup_link(target, setup_token),
        )

    async def delete_tenant_user(
        self, current_user: User, tenant_id: int, user_id: UUID, background_tasks: BackgroundTasks
    ) -> None:
        await self.enforce_scope(current_user, tenant_id)
        tenant = await self._load_tenant_or_404(tenant_id)
        target = await self._load_tenant_user_or_404(tenant_id, user_id)
        # MODERATORs may delete USER-role accounts but not higher-privileged roles.
        target_roles = await self._roles.get_user_roles(target.id)
        if RoleName.TENANT_ADMIN.value in target_roles:
            await self._deny_moderator(current_user)
        await self._assert_not_last_tenant_admin(target, tenant)

        # Capture PII before anonymisation — enqueue_email is called after commit
        # so a failed update/commit cannot leak a deletion email.
        deleted_email = target.email
        deleted_full_name = target.full_name

        await self._users.update(
            target,
            {
                "is_delete": True,
                "is_active": False,
                "full_name": f"del_{target.id}",
                "username": f"del_{target.id}",
                "prev_email": target.email,
                "email": f"del_{target.id}",
                "prev_phone_number": target.phone_number,
                "phone_number": None,
                "updated_by": current_user.id,
            },
        )
        if self._refresh_tokens is not None:
            await self._refresh_tokens.delete_by_user_id(target.id)
        await self._users.commit()

        enqueue_email(
            background_tasks,
            self._email,
            lambda: render_account_deleted(deleted_email, deleted_full_name),
        )
        # No per-user API key eviction: keys belong to Applications, not
        # Users (migration e9f0a1b2c3d4) — deleting a tenant user has no
        # bearing on any key's cache.
