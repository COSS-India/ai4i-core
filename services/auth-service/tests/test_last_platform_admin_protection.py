"""Unit tests: the sole active ADMIN in the Default Organization cannot be
suspended or deleted, but is protected only there and only while active."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.constants import RoleName
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


def _make_service() -> TenantService:
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock()
    tenant_repo._db = MagicMock()
    tenant_repo._db.execute = AsyncMock()
    user_repo = MagicMock()
    user_repo.update = AsyncMock()
    user_repo.save_and_refresh = AsyncMock()
    user_repo.commit = AsyncMock()
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=[])
    role_service.count_admins_in_tenant = AsyncMock(return_value=2)
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _admin_user(*, is_active: bool = True) -> User:
    return User(
        id=uuid4(),
        email="test-admin@example.invalid",
        username=uuid4().hex[:12],
        tenant_id=1,
        is_active=is_active,
    )


def _default_org() -> Tenant:
    return Tenant(
        id=1,
        name="Default Organization",
        organisation="default organisation",
        email="test-contact@example.invalid",
        status=TenantStatus.ACTIVE,
    )


def _other_tenant() -> Tenant:
    return Tenant(
        id=2,
        name="Acme",
        organisation="Acme",
        email="test-other-contact@example.invalid",
        status=TenantStatus.ACTIVE,
    )


class TestAssertNotLastPlatformAdmin:
    @pytest.mark.asyncio
    async def test_blocks_when_sole_active_admin(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)
        target = _admin_user()

        with pytest.raises(HTTPException) as exc_info:
            await svc._assert_not_last_platform_admin(target, _default_org(), action="suspend")

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "LAST_PLATFORM_ADMIN"
        assert "Cannot suspend the only Admin in the Default Organization" in exc_info.value.detail["message"]

    @pytest.mark.asyncio
    async def test_delete_message_matches_action(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)
        target = _admin_user()

        with pytest.raises(HTTPException) as exc_info:
            await svc._assert_not_last_platform_admin(target, _default_org(), action="delete")

        assert "Cannot delete the only Admin in the Default Organization" in exc_info.value.detail["message"]

    @pytest.mark.asyncio
    async def test_allowed_when_multiple_active_admins(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=2)
        target = _admin_user()

        await svc._assert_not_last_platform_admin(target, _default_org(), action="suspend")

        svc._roles.count_admins_in_tenant.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_skipped_outside_default_organization(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)
        target = _admin_user()

        await svc._assert_not_last_platform_admin(target, _other_tenant(), action="delete")

        svc._roles.count_admins_in_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skipped_when_target_not_admin(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.MODERATOR.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)
        target = _admin_user()

        await svc._assert_not_last_platform_admin(target, _default_org(), action="delete")

        svc._roles.count_admins_in_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skipped_when_target_already_inactive(self) -> None:
        """An already-suspended/deleted admin isn't part of the active count,
        so acting on them further can't be what drops it to zero."""
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)
        target = _admin_user(is_active=False)

        await svc._assert_not_last_platform_admin(target, _default_org(), action="delete")

        svc._roles.get_user_roles.assert_not_awaited()
        svc._roles.count_admins_in_tenant.assert_not_awaited()


class TestUpdateTenantUserStatusPlatformAdminGuard:
    @pytest.mark.asyncio
    async def test_suspend_blocked_for_sole_active_admin(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        target = _admin_user()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)

        body = MagicMock()
        body.is_active = False

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant_user_status(_admin_user(), 1, target.id, body)

        assert exc_info.value.detail["code"] == "LAST_PLATFORM_ADMIN"
        svc._users.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_suspend_allowed_when_another_active_admin_exists(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        target = _admin_user()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=2)

        body = MagicMock()
        body.is_active = False

        await svc.update_tenant_user_status(_admin_user(), 1, target.id, body)

        svc._users.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reactivating_sole_admin_is_not_blocked(self) -> None:
        """is_active=True is a reactivation, not a removal — the guard only fires on suspend."""
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        target = _admin_user(is_active=False)
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)

        body = MagicMock()
        body.is_active = True

        await svc.update_tenant_user_status(_admin_user(), 1, target.id, body)

        svc._users.update.assert_awaited_once()


class TestDeleteTenantUserPlatformAdminGuard:
    @pytest.mark.asyncio
    async def test_delete_blocked_for_sole_active_admin(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        target = _admin_user()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)

        with pytest.raises(HTTPException) as exc_info:
            await svc.delete_tenant_user(_admin_user(), 1, target.id, MagicMock())

        assert exc_info.value.detail["code"] == "LAST_PLATFORM_ADMIN"
        svc._users.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_allowed_when_another_active_admin_exists(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        target = _admin_user()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=2)

        await svc.delete_tenant_user(_admin_user(), 1, target.id, MagicMock())

        svc._users.update.assert_awaited_once()
        svc._users.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_allowed_for_already_suspended_admin(self) -> None:
        """Deleting an admin who is already inactive can't lower the active
        count further, so it must be allowed even with only one active admin."""
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        target = _admin_user(is_active=False)
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)

        await svc.delete_tenant_user(_admin_user(), 1, target.id, MagicMock())

        svc._users.update.assert_awaited_once()
        svc._users.commit.assert_awaited_once()
