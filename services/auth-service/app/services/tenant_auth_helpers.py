"""Tenant lifecycle checks for authentication flows."""

from typing import Optional

from app.core.exceptions import AuthorizationError

from app.models.tenant import Tenant, TenantStatus


def assert_tenant_allows_authentication(tenant: Optional[Tenant]) -> None:
    """Reject sign-in when the tenant is not ACTIVE."""
    if tenant is None:
        return

    if tenant.status == TenantStatus.ACTIVE:
        return

    if tenant.status == TenantStatus.PENDING:
        raise AuthorizationError(
            message="Tenant status is pending. Complete tenant activation before signing in.",
            code="TENANT_INACTIVE",
        )
    if tenant.status == TenantStatus.SUSPENDED:
        raise AuthorizationError(
            message="Your account access has been suspended. Please contact support.",
            code="TENANT_SUSPENDED",
        )
    raise AuthorizationError(
        message="Tenant is deactivated.",
        code="TENANT_INACTIVE",
    )


def assert_tenant_allows_onboarding(tenant: Optional[Tenant]) -> None:
    """Allow email verification and password setup while tenant is PENDING or ACTIVE."""
    if tenant is None:
        return

    if tenant.status in (TenantStatus.PENDING, TenantStatus.ACTIVE):
        return

    if tenant.status == TenantStatus.SUSPENDED:
        raise AuthorizationError(
            message="Your account access has been suspended. Please contact support.",
            code="TENANT_SUSPENDED",
        )
    raise AuthorizationError(
        message="Tenant is deactivated.",
        code="TENANT_INACTIVE",
    )
