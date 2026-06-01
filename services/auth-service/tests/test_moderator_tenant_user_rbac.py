"""Unit tests: Moderator is blocked from update_tenant_user and update_tenant_user_status."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.role_name import RoleName
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


def _make_service() -> TenantService:
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock()
    user_repo = MagicMock()
    user_repo.save_and_refresh = AsyncMock()
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=[])
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _moderator() -> User:
    return User(id=uuid4(), email="mod@example.com", username="moderator")


def _admin() -> User:
    return User(id=uuid4(), email="admin@example.com", username="admin")


def _tenant_user() -> User:
    return User(id=uuid4(), email="user@tenant.com", username="tuser", tenant_id=1)


def _active_tenant() -> Tenant:
    return Tenant(id=1, name="Acme", organisation="Acme", email="c@acme.com",
                  status=TenantStatus.ACTIVE)


class TestModeratorUpdateTenantUser:
    @pytest.mark.asyncio
    async def test_moderator_cannot_update_tenant_user(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.MODERATOR.value])

        body = MagicMock()
        body.model_dump.return_value = {"full_name": "Forbidden Update"}

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant_user(_moderator(), 1, uuid4(), body)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"
        svc._tenants.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_can_update_tenant_user(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        target = _tenant_user()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.save_and_refresh = AsyncMock()

        body = MagicMock()
        body.model_dump.return_value = {"full_name": "Allowed Update"}

        await svc.update_tenant_user(_admin(), 1, target.id, body)

        svc._users.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_moderator_cannot_update_tenant_user_status(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.MODERATOR.value])

        body = MagicMock()
        body.model_dump.return_value = {"is_active": False}

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant_user_status(_moderator(), 1, uuid4(), body)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"
        svc._tenants.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_can_update_tenant_user_status(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        target = _tenant_user()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.save_and_refresh = AsyncMock()

        body = MagicMock()
        body.model_dump.return_value = {"is_active": True}

        await svc.update_tenant_user_status(_admin(), 1, target.id, body)

        svc._users.update.assert_awaited_once()
