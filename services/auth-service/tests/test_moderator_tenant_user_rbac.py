"""Unit tests: Moderator is blocked from list, create, update, and update-status on tenant users."""

from unittest.mock import AsyncMock, MagicMock, patch
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
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _moderator() -> User:
    return User(id=uuid4(), email="test-moderator@example.invalid", username=uuid4().hex[:12])


def _admin() -> User:
    return User(id=uuid4(), email="test-admin@example.invalid", username=uuid4().hex[:12])


def _tenant_user() -> User:
    return User(id=uuid4(), email="test-tenant-user@example.invalid", username=uuid4().hex[:12], tenant_id=1)


def _active_tenant() -> Tenant:
    return Tenant(id=1, name="Acme", organisation="Acme", email="test-contact@example.invalid",
                  status=TenantStatus.ACTIVE)


class TestModeratorListTenantUsers:
    @pytest.mark.asyncio
    async def test_moderator_cannot_list_tenant_users(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.MODERATOR.value])

        with pytest.raises(HTTPException) as exc_info:
            await svc.list_tenant_users(_moderator(), 1, offset=0, limit=20)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"
        svc._users.list_by_tenant.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_can_list_tenant_users(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._users.list_by_tenant = AsyncMock(return_value=[])

        result = await svc.list_tenant_users(_admin(), 1, offset=0, limit=20)

        assert result == []
        svc._users.list_by_tenant.assert_awaited_once_with(1, offset=0, limit=20)


class TestModeratorCreateTenantUser:
    @pytest.mark.asyncio
    async def test_moderator_cannot_create_tenant_user(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.MODERATOR.value])

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_tenant_user(_moderator(), 1, MagicMock(), MagicMock())

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"
        svc._tenants.get_by_id_for_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_can_create_tenant_user(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_active_tenant())
        svc.provision_user = AsyncMock(return_value=("user-id-123", "setup-token-abc"))

        body = MagicMock()
        body.email = "test-new-user@example.invalid"
        body.full_name = "New User"
        body.phone_number = None
        body.role.value = "TENANT USER"

        with patch(
            "app.services.tenant_service.allocate_unique_username",
            new_callable=AsyncMock,
            return_value="newuser",
        ):
            result = await svc.create_tenant_user(_admin(), 1, body, MagicMock())

        assert result == ("user-id-123", "setup-token-abc")
        svc.provision_user.assert_awaited_once()


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


class TestModeratorDeleteTenantUser:
    @pytest.mark.asyncio
    async def test_moderator_cannot_delete_tenant_user(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.MODERATOR.value])

        with pytest.raises(HTTPException) as exc_info:
            await svc.delete_tenant_user(_moderator(), 1, uuid4())

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"
        svc._tenants.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_can_delete_tenant_user(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        target = _tenant_user()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.commit = AsyncMock()

        await svc.delete_tenant_user(_admin(), 1, target.id)

        svc._users.update.assert_awaited_once()
        svc._users.commit.assert_awaited_once()
