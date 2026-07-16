"""Unit tests for the ?unmask PII policy + role gating on tenant GET endpoints.

Covers:
  * ``TenantService.build_tenant_response`` masking policy — default masks
    both; ``unmask`` reveals the phone always and the email only while PENDING.
  * Role gating for ``unmask``: only ADMIN / TENANT ADMIN may reveal cleartext
    PII. Moderators and plain tenant users are refused even though they can read
    the masked values.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


def _tenant(status: TenantStatus = TenantStatus.ACTIVE) -> Tenant:
    return Tenant(
        id=1,
        name="Acme Contact",
        organisation="Acme",
        email="john.doe@example.com",
        phone_number="+919876543210",
        status=status,
        created_at=datetime.now(timezone.utc),
    )


def _make_service() -> TenantService:
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock()
    user_repo = MagicMock()
    user_repo.list_by_tenant = AsyncMock(return_value=[])
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=[])
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _user(tenant_id=None) -> User:
    return User(id=uuid4(), email="x@example.com", username="x", tenant_id=tenant_id)


class TestBuildTenantResponse:
    def test_masks_both_by_default(self) -> None:
        out = TenantService.build_tenant_response(_tenant())
        assert out["email"] == "j***@e***.com"
        assert out["phone_number"] == "*********3210"

    def test_unmask_active_reveals_phone_but_keeps_email_masked(self) -> None:
        # Not PENDING → email stays masked, phone revealed.
        out = TenantService.build_tenant_response(
            _tenant(TenantStatus.ACTIVE), unmask=True
        )
        assert out["phone_number"] == "+919876543210"
        assert out["email"] == "j***@e***.com"

    def test_unmask_pending_reveals_phone_and_email(self) -> None:
        # PENDING → both revealed (email may still be corrected pre-verification).
        out = TenantService.build_tenant_response(
            _tenant(TenantStatus.PENDING), unmask=True
        )
        assert out["phone_number"] == "+919876543210"
        assert out["email"] == "john.doe@example.com"


class TestGetTenantUnmaskGating:
    @pytest.mark.asyncio
    async def test_moderator_cannot_unmask(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["MODERATOR"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())

        with pytest.raises(HTTPException) as exc:
            await svc.get_tenant(_user(), 1, unmask=True)

        assert exc.value.status_code == 403
        # Gated before the tenant is even loaded.
        svc._tenants.get_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_moderator_can_still_read_masked(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["MODERATOR"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())

        tenant = await svc.get_tenant(_user(), 1, unmask=False)

        assert tenant is not None
        svc._tenants.get_by_id.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_plain_tenant_user_cannot_unmask(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())

        with pytest.raises(HTTPException) as exc:
            await svc.get_tenant(_user(tenant_id=1), 1, unmask=True)

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_unmask(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())

        tenant = await svc.get_tenant(_user(), 1, unmask=True)

        assert tenant is not None

    @pytest.mark.asyncio
    async def test_tenant_admin_can_unmask_own_tenant(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())

        tenant = await svc.get_tenant(_user(tenant_id=1), 1, unmask=True)

        assert tenant is not None


class TestListTenantUsersUnmaskGating:
    @pytest.mark.asyncio
    async def test_plain_tenant_user_cannot_unmask(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())

        with pytest.raises(HTTPException) as exc:
            await svc.list_tenant_users(
                _user(tenant_id=1), 1, offset=0, limit=100, unmask=True
            )

        assert exc.value.status_code == 403
        svc._users.list_by_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_plain_tenant_user_can_list_masked(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        svc._users.list_by_tenant = AsyncMock(return_value=[])

        result = await svc.list_tenant_users(
            _user(tenant_id=1), 1, offset=0, limit=100, unmask=False
        )

        assert result == []
        svc._users.list_by_tenant.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tenant_admin_can_unmask(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        svc._users.list_by_tenant = AsyncMock(return_value=[])

        result = await svc.list_tenant_users(
            _user(tenant_id=1), 1, offset=0, limit=100, unmask=True
        )

        assert result == []
        svc._users.list_by_tenant.assert_awaited_once()
