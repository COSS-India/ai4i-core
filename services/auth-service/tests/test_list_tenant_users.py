"""Unit tests for GET /api/v1/tenants/{tenant_id}/users — tenant existence check."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import EntityNotFoundError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


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


def _admin() -> User:
    return User(id=uuid4(), email="admin@example.com", username="admin")


class TestListTenantUsers:
    @pytest.mark.asyncio
    async def test_nonexistent_tenant_raises_404(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(EntityNotFoundError):
            await svc.list_tenant_users(_admin(), 99999, offset=0, limit=100)

        svc._users.list_by_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_existing_tenant_with_no_users_returns_empty_list(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(return_value=Tenant(
            id=1, name="Acme", organisation="Acme", email="c@acme.com",
            status=TenantStatus.ACTIVE,
        ))
        svc._users.list_by_tenant = AsyncMock(return_value=[])

        result = await svc.list_tenant_users(_admin(), 1, offset=0, limit=100)

        assert result == []
        svc._users.list_by_tenant.assert_awaited_once_with(1, offset=0, limit=100)
