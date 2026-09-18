"""Unit tests: the sole active ADMIN in the Default Organization cannot be
suspended or deleted, but is protected only there and only while active."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import AppError
from app.core.constants import RoleName
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.role_service import RoleService
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
    role_repo = MagicMock()
    role_repo.count_admins_in_tenant = AsyncMock(return_value=2)
    role_service = RoleService(role_repo, MagicMock(), MagicMock())
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
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=1)
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
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=1)
        target = _admin_user()

        with pytest.raises(HTTPException) as exc_info:
            await svc._assert_not_last_platform_admin(target, _default_org(), action="delete")

        assert "Cannot delete the only Admin in the Default Organization" in exc_info.value.detail["message"]

    @pytest.mark.asyncio
    async def test_allowed_when_multiple_active_admins(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=2)
        target = _admin_user()

        await svc._assert_not_last_platform_admin(target, _default_org(), action="suspend")

        svc._roles._roles.count_admins_in_tenant.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_skipped_outside_default_organization(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=1)
        target = _admin_user()

        await svc._assert_not_last_platform_admin(target, _other_tenant(), action="delete")

        svc._roles._roles.count_admins_in_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skipped_when_target_not_admin(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.MODERATOR.value])
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=1)
        target = _admin_user()

        await svc._assert_not_last_platform_admin(target, _default_org(), action="delete")

        svc._roles._roles.count_admins_in_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skipped_when_target_already_inactive(self) -> None:
        """An already-suspended/deleted admin isn't part of the active count,
        so acting on them further can't be what drops it to zero."""
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=1)
        target = _admin_user(is_active=False)

        await svc._assert_not_last_platform_admin(target, _default_org(), action="delete")

        svc._roles.get_user_roles.assert_not_awaited()
        svc._roles._roles.count_admins_in_tenant.assert_not_awaited()


class TestUpdateTenantUserStatusPlatformAdminGuard:
    @pytest.mark.asyncio
    async def test_suspend_blocked_for_sole_active_admin(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        target = _admin_user()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=1)

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
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=2)

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
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=1)

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
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=1)

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
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=2)

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
        svc._roles._roles.count_admins_in_tenant = AsyncMock(return_value=1)

        await svc.delete_tenant_user(_admin_user(), 1, target.id, MagicMock())

        svc._users.update.assert_awaited_once()
        svc._users.commit.assert_awaited_once()


def _make_role_service() -> RoleService:
    role_repo = MagicMock()
    role_repo._db = MagicMock()
    role_repo._db.execute = AsyncMock()
    role_repo.commit = AsyncMock()
    role_repo.get_role_by_name = AsyncMock(
        return_value=MagicMock(id=1, name=RoleName.ADMIN.value)
    )
    role_repo.get_user_role_record = AsyncMock(return_value=None)
    role_repo.assign_role = AsyncMock()
    role_repo.remove_role = AsyncMock(return_value=True)
    role_repo.count_admins_in_tenant = AsyncMock(return_value=2)
    user_repo = MagicMock()
    tenant_repo = MagicMock()
    return RoleService(role_repo, user_repo, tenant_repo)


class TestRoleServiceRemoveRoleGuardsSolePlatformAdmin:
    """`/roles/remove` is a second path (besides suspend/delete) that can drop a
    user's ADMIN role — the Institution Management role dropdown demotes by
    assigning the new role then removing ADMIN, bypassing both TenantService
    guards entirely. This is the authoritative check for that path."""

    @pytest.mark.asyncio
    async def test_blocks_removing_admin_from_sole_active_admin(self) -> None:
        svc = _make_role_service()
        target = _admin_user()
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)

        with pytest.raises(AppError) as exc_info:
            await svc.remove_role(target.id, RoleName.ADMIN)

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "LAST_PLATFORM_ADMIN"
        svc._roles.remove_role.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_allows_removing_admin_when_another_active_admin_exists(self) -> None:
        svc = _make_role_service()
        target = _admin_user()
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=2)

        await svc.remove_role(target.id, RoleName.ADMIN)

        svc._roles.remove_role.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skipped_outside_default_organization(self) -> None:
        svc = _make_role_service()
        target = _admin_user()
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._tenants.get_by_id = AsyncMock(return_value=_other_tenant())
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)

        await svc.remove_role(target.id, RoleName.ADMIN)

        svc._roles.count_admins_in_tenant.assert_not_awaited()
        svc._roles.remove_role.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skipped_when_target_already_inactive(self) -> None:
        svc = _make_role_service()
        target = _admin_user(is_active=False)
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())
        svc._roles.count_admins_in_tenant = AsyncMock(return_value=1)

        await svc.remove_role(target.id, RoleName.ADMIN)

        svc._tenants.get_by_id.assert_not_awaited()
        svc._roles.count_admins_in_tenant.assert_not_awaited()
        svc._roles.remove_role.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_applied_to_non_admin_roles(self) -> None:
        svc = _make_role_service()
        svc._roles.get_role_by_name = AsyncMock(
            return_value=MagicMock(id=2, name=RoleName.MODERATOR.value)
        )
        svc._users.get_by_id = AsyncMock()

        await svc.remove_role(uuid4(), RoleName.MODERATOR)

        svc._users.get_by_id.assert_not_awaited()
        svc._roles.remove_role.assert_awaited_once()


class TestRoleServiceAssignRoleLocksAdminRoster:
    """Promoting to ADMIN takes the same advisory lock as the removal guard,
    so a concurrent promote/demote pair on the Default Organization can't
    interleave around the last-admin count."""

    @pytest.mark.asyncio
    async def test_assigning_admin_takes_the_lock_in_default_org(self) -> None:
        svc = _make_role_service()
        target = _admin_user()
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._tenants.get_by_id = AsyncMock(return_value=_default_org())

        await svc.assign_role(target.id, RoleName.ADMIN)

        svc._roles._db.execute.assert_awaited_once()
        svc._roles.assign_role.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assigning_admin_outside_default_org_skips_lock(self) -> None:
        svc = _make_role_service()
        target = _admin_user()
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._tenants.get_by_id = AsyncMock(return_value=_other_tenant())

        await svc.assign_role(target.id, RoleName.ADMIN)

        svc._roles._db.execute.assert_not_awaited()
        svc._roles.assign_role.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assigning_non_admin_role_skips_lock(self) -> None:
        svc = _make_role_service()
        svc._roles.get_role_by_name = AsyncMock(
            return_value=MagicMock(id=2, name=RoleName.MODERATOR.value)
        )
        svc._users.get_by_id = AsyncMock()

        await svc.assign_role(uuid4(), RoleName.MODERATOR)

        svc._users.get_by_id.assert_not_awaited()
        svc._roles.assign_role.assert_awaited_once()
