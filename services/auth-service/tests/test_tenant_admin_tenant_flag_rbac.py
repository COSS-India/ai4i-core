"""Unit tests: Tenant Admin cannot set is_tenant_active via PATCH status (AI4IDS-1763)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.role_name import RoleName
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.schemas.tenant import TenantUserStatusUpdate
from app.services.tenant_service import TenantService


def _make_service() -> TenantService:
    tenant_repo = MagicMock()
    user_repo = MagicMock()
    user_repo.save_and_refresh = AsyncMock()
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


def _tenant_admin() -> User:
    return User(id=uuid4(), email="tadmin@tenant.com", username="tadmin", tenant_id=1)


def _admin() -> User:
    return User(id=uuid4(), email="admin@example.com", username="admin")


def _active_tenant() -> Tenant:
    return Tenant(id=1, name="Acme", organisation="Acme", email="c@acme.com",
                  status=TenantStatus.ACTIVE)


def _target_user() -> User:
    return User(id=uuid4(), email="user@tenant.com", username="tuser",
                tenant_id=1, is_active=True, is_tenant_active=True)


class TestTenantAdminTenantFlagRBAC:
    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_set_is_tenant_active_false(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.TENANT_ADMIN.value])

        body = TenantUserStatusUpdate(is_tenant_active=False)
        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant_user_status(_tenant_admin(), 1, uuid4(), body)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"
        svc._tenants.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_set_is_tenant_active_true(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.TENANT_ADMIN.value])

        body = TenantUserStatusUpdate(is_active=True, is_tenant_active=True)
        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant_user_status(_tenant_admin(), 1, uuid4(), body)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"

    @pytest.mark.asyncio
    async def test_tenant_admin_can_set_only_is_active(self) -> None:
        target = _target_user()
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.TENANT_ADMIN.value])
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.save_and_refresh = AsyncMock()

        body = TenantUserStatusUpdate(is_active=False)
        await svc.update_tenant_user_status(_tenant_admin(), 1, target.id, body)

        svc._users.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_admin_can_set_is_tenant_active(self) -> None:
        target = _target_user()
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.save_and_refresh = AsyncMock()

        body = TenantUserStatusUpdate(is_tenant_active=False)
        await svc.update_tenant_user_status(_admin(), 1, target.id, body)

        svc._users.update.assert_awaited_once()
