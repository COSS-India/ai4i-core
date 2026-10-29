"""Tenant status transition rules and user-flag sync (shared by auth + tenant services)."""

from typing import Optional
from uuid import UUID

from app.core.config import settings
from app.core.exceptions import AppError, EntityNotFoundError, ValidationError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository

# PATCH /tenants/{id}/status and onboarding (PENDING → ACTIVE on set-password).
ALLOWED_TENANT_STATUS_TRANSITIONS: dict[TenantStatus, frozenset[TenantStatus]] = {
    TenantStatus.PENDING: frozenset({TenantStatus.DEACTIVATED}),
    TenantStatus.ACTIVE: frozenset({TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED}),
    TenantStatus.SUSPENDED: frozenset({TenantStatus.ACTIVE, TenantStatus.DEACTIVATED}),
    TenantStatus.DEACTIVATED: frozenset({TenantStatus.ACTIVE}),
}

# Statuses during which a tenant's users may still complete onboarding (set
# password). PENDING is included: the contact admin onboards before the tenant
# is ACTIVE, and setting their password is what activates the tenant. Shared by
# the set-password guard (AuthService.assert_tenant_allows_onboarding) and the
# resend-setup-link endpoint so the two windows can never drift.
TENANT_ONBOARDING_STATUSES: frozenset[TenantStatus] = frozenset(
    {TenantStatus.PENDING, TenantStatus.ACTIVE}
)


def is_default_tenant(tenant: Tenant) -> bool:
    """True if ``tenant`` is the seeded Default Organisation (matched by ``organisation``, case-insensitive)."""
    return tenant.organisation.strip().casefold() == settings.default_tenant_org.strip().casefold()


def assert_default_tenant_not_targeted(
    tenant: Tenant, *, message: Optional[str] = None
) -> None:
    """Raise ValidationError (code ``DEFAULT_ORG_PROTECTED``) if ``tenant`` is the Default Organisation.

    The Default Organisation is the fallback tenant for direct portal
    signups and must always stay ACTIVE, keep its name, and have no TENANT
    ADMIN — suspending, deactivating, renaming, or handing out TENANT ADMIN
    there would strand that fallback path.
    """
    if is_default_tenant(tenant):
        raise ValidationError(
            message=message or "This action is not allowed for the Default Organisation.",
            code="DEFAULT_ORG_PROTECTED",
        )


async def assert_tenant_admin_assignable(
    tenant_repo: TenantRepository, tenant_id: Optional[int]
) -> None:
    """Raise if ``tenant_id`` belongs to the Default Organisation, or doesn't resolve to a tenant at all.

    Fails closed: a ``tenant_id`` that no longer resolves to a row is an
    anomaly this guard cannot vouch for, so it rejects rather than letting
    the assignment through unchecked.
    """
    if tenant_id is None:
        return
    tenant = await tenant_repo.get_by_id(tenant_id)
    if tenant is None:
        raise EntityNotFoundError(f"Tenant {tenant_id}")
    assert_default_tenant_not_targeted(tenant)


def assert_valid_tenant_status_transition(
    current: TenantStatus,
    target: TenantStatus,
) -> None:
    """Raise ValidationError when ``target`` is not allowed from ``current``."""
    if current == target:
        raise ValidationError(
            message=f"Tenant status is already {current.value}.",
            code="TENANT_STATUS_UNCHANGED",
        )
    allowed = ALLOWED_TENANT_STATUS_TRANSITIONS.get(current, frozenset())
    if target in allowed:
        return
    allowed_labels = ", ".join(sorted(s.value for s in allowed)) or "none"
    raise ValidationError(
        message=(
            f"Cannot change tenant status from {current.value} to {target.value}. "
            f"Allowed targets: {allowed_labels}."
        ),
        code="INVALID_TENANT_STATUS_TRANSITION",
    )


async def sync_tenant_users_for_status(
    user_repo: UserRepository,
    tenant_id: int,
    status: TenantStatus,
    updated_by: Optional[UUID] = None,
) -> None:
    """Sync ``is_tenant_active`` for all tenant users when platform tenant status changes."""
    if status == TenantStatus.ACTIVE:
        await user_repo.unlock_tenant_users_for_status(
            tenant_id, updated_by=updated_by
        )
    elif status in (TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED):
        await user_repo.lock_tenant_users_for_status(tenant_id, updated_by=updated_by)


# ── Institution contact changes ──────────────────────────────────────

#: Contact changes are refused for these statuses; other fields stay editable.
EMAIL_LOCKED_STATUSES: frozenset[TenantStatus] = frozenset(
    {TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED}
)


def assert_tenant_email_editable(tenant: Tenant) -> None:
    """409 TENANT_EMAIL_EDIT_NOT_ALLOWED while SUSPENDED/DEACTIVATED, and for
    the Default Organisation (its contact is the seeded platform admin)."""
    if tenant.status in EMAIL_LOCKED_STATUSES:
        message = (
            "The contact cannot be changed while the institution "
            f"is {tenant.status.value.lower()}."
        )
    elif is_default_tenant(tenant):
        message = "The Default Organisation's contact cannot be changed."
    else:
        return
    raise AppError(message=message, code="TENANT_EMAIL_EDIT_NOT_ALLOWED", status_code=409)


async def assert_email_available(
    tenant_repo: TenantRepository,
    user_repo: UserRepository,
    email: str,
    tenant_id: int,
    admin: Optional[User],
) -> None:
    """Single, admin-aware email-uniqueness check. Consolidates what
    PR #828 added (cross-tenant tenant+user collision) with the
    reissue-time check this PR needed (any non-admin user collision),
    so there is exactly one query per table and one place that owns
    email uniqueness for tenant email changes.
    """
    existing_tenant = await tenant_repo.get_by_email(email)
    if existing_tenant and existing_tenant.id != tenant_id:
        raise AppError(
            message="A tenant with this email already exists.",
            code="DUPLICATE_TENANT_EMAIL",
            status_code=409,
        )
    existing_user = await user_repo.get_by_email(email)
    if existing_user is None:
        return
    if admin is not None:
        # ``admin.email`` will become ``email``. Any other holder — same-tenant
        # or cross-tenant — breaks the users.email UNIQUE constraint at flush
        # time, so only the admin themselves is an allowed match.
        collides = existing_user.id != admin.id
    else:
        # No user re-aligned: tenant.email is independent of users.email, so
        # a same-tenant user happening to share the address is harmless.
        # Only reject cross-tenant.
        collides = existing_user.tenant_id != tenant_id
    if collides:
        raise AppError(
            message="This email is already in use.",
            code="DUPLICATE_EMAIL",
            status_code=409,
        )
