"""Tenant status transition rules and user-flag sync (shared by auth + tenant services)."""

from typing import Optional
from uuid import UUID

from app.core.exceptions import ValidationError
from app.models.tenant import TenantStatus
from app.repositories.user_repository import UserRepository

# PATCH /tenants/{id}/status and onboarding (PENDING → ACTIVE on set-password).
ALLOWED_TENANT_STATUS_TRANSITIONS: dict[TenantStatus, frozenset[TenantStatus]] = {
    TenantStatus.PENDING: frozenset({TenantStatus.ACTIVE}),
    TenantStatus.ACTIVE: frozenset({TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED}),
    TenantStatus.SUSPENDED: frozenset({TenantStatus.ACTIVE, TenantStatus.DEACTIVATED}),
    TenantStatus.DEACTIVATED: frozenset({TenantStatus.ACTIVE}),
}


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
