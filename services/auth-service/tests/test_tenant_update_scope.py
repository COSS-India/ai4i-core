"""Scope enforcement on PATCH /api/v1/tenants/{id} (profile update).

TENANT ADMIN holds tenant.update (perm 42), shared at the gateway with the
status endpoint, so update_tenant must restrict non-admins to their own tenant
(AI4IDS-1750) — otherwise a Tenant Admin could edit any tenant by id.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


def _make_service(roles: list[str]) -> TenantService:
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=roles)
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock(
        return_value=Tenant(id=1, name="C", organisation="Acme",
                            email="c@acme.com", status=TenantStatus.ACTIVE)
    )
    tenant_repo.update = AsyncMock()
    tenant_repo.save_and_refresh = AsyncMock()
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=MagicMock(),
        role_service=role_service,
        verification_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _user(tenant_id: int | None) -> User:
    u = User(id=uuid4(), email="a@b.com", username="u")
    u.tenant_id = tenant_id
    return u


def _body() -> MagicMock:
    body = MagicMock()
    body.model_dump.return_value = {"contact_name": "New Name"}
    return body


class TestUpdateTenantScope:
    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self) -> None:
        """Non-admin patching a tenant that isn't theirs -> 403, no write."""
        svc = _make_service(roles=[])  # plain TENANT ADMIN style: no system-admin role
        with pytest.raises(HTTPException) as exc:
            await svc.update_tenant(_user(tenant_id=2), 1, _body())
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "TENANT_FORBIDDEN"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_own_tenant_allowed(self) -> None:
        """Non-admin patching their own tenant -> proceeds."""
        svc = _make_service(roles=[])
        await svc.update_tenant(_user(tenant_id=1), 1, _body())
        svc._tenants.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_system_admin_any_tenant_allowed(self) -> None:
        """ADMIN passes enforce_scope for any tenant."""
        svc = _make_service(roles=["ADMIN"])
        await svc.update_tenant(_user(tenant_id=999), 1, _body())
        svc._tenants.update.assert_awaited_once()
