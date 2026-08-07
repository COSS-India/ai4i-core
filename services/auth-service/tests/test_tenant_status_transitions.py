"""Tenant status transition rules and user-flag sync."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.exceptions import EntityNotFoundError, ValidationError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.schemas.tenant import TenantUpdate, TenantUserCreate, TenantUserRole, TenantUserUpdate
from app.services.tenant_lifecycle import (
    assert_default_tenant_not_targeted,
    assert_tenant_admin_assignable,
    assert_valid_tenant_status_transition,
    is_default_tenant,
    sync_tenant_users_for_status,
)
from app.services.tenant_service import (
    TenantService,
    _assert_tenant_active_for_user_deactivation,
)


class TestTenantStatusTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (TenantStatus.PENDING, TenantStatus.DEACTIVATED),
            (TenantStatus.ACTIVE, TenantStatus.SUSPENDED),
            (TenantStatus.ACTIVE, TenantStatus.DEACTIVATED),
            (TenantStatus.SUSPENDED, TenantStatus.ACTIVE),
            (TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED),
            (TenantStatus.DEACTIVATED, TenantStatus.ACTIVE),
        ],
    )
    def test_allowed_transitions(self, current: TenantStatus, target: TenantStatus) -> None:
        assert_valid_tenant_status_transition(current, target)

    def test_same_status_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            assert_valid_tenant_status_transition(TenantStatus.ACTIVE, TenantStatus.ACTIVE)
        assert exc_info.value.code == "TENANT_STATUS_UNCHANGED"
        assert "ACTIVE" in exc_info.value.message

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (TenantStatus.PENDING, TenantStatus.SUSPENDED),
            (TenantStatus.PENDING, TenantStatus.ACTIVE),
            (TenantStatus.ACTIVE, TenantStatus.PENDING),
            (TenantStatus.SUSPENDED, TenantStatus.PENDING),
            (TenantStatus.DEACTIVATED, TenantStatus.SUSPENDED),
            (TenantStatus.DEACTIVATED, TenantStatus.PENDING),
        ],
    )
    def test_disallowed_transitions_raise(self, current: TenantStatus, target: TenantStatus) -> None:
        with pytest.raises(ValidationError) as exc_info:
            assert_valid_tenant_status_transition(current, target)
        assert exc_info.value.code == "INVALID_TENANT_STATUS_TRANSITION"
        assert current.value in exc_info.value.message
        assert target.value in exc_info.value.message


class TestSyncTenantUsersForStatus:
    @pytest.mark.asyncio
    async def test_active_unlocks_tenant_users(self) -> None:
        user_repo = AsyncMock()
        updated_by = uuid4()
        await sync_tenant_users_for_status(
            user_repo, 1, TenantStatus.ACTIVE, updated_by=updated_by
        )
        user_repo.unlock_tenant_users_for_status.assert_awaited_once_with(
            1, updated_by=updated_by
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED])
    async def test_suspended_or_deactivated_locks_tenant_users(
        self, status: TenantStatus
    ) -> None:
        user_repo = AsyncMock()
        updated_by = uuid4()
        await sync_tenant_users_for_status(user_repo, 2, status, updated_by=updated_by)
        user_repo.lock_tenant_users_for_status.assert_awaited_once_with(
            2, updated_by=updated_by
        )

    @pytest.mark.asyncio
    async def test_pending_does_not_update_users(self) -> None:
        user_repo = AsyncMock()
        await sync_tenant_users_for_status(user_repo, 3, TenantStatus.PENDING)
        user_repo.unlock_tenant_users_for_status.assert_not_awaited()
        user_repo.lock_tenant_users_for_status.assert_not_awaited()


class TestTenantUserStatusPayload:
    def test_deactivate_user_requires_active_tenant(self) -> None:
        tenant = Tenant(id=1, status=TenantStatus.SUSPENDED)
        with pytest.raises(ValidationError) as exc_info:
            _assert_tenant_active_for_user_deactivation(tenant, {"is_active": False})
        assert exc_info.value.code == "TENANT_NOT_ACTIVE"

    def test_activate_user_skips_tenant_active_check(self) -> None:
        tenant = Tenant(id=1, status=TenantStatus.SUSPENDED)
        _assert_tenant_active_for_user_deactivation(tenant, {"is_active": True})


def _status_body(status: TenantStatus) -> MagicMock:
    body = MagicMock()
    body.status = status
    return body


def _tenant_service_with_mocks() -> TenantService:
    user_repo = MagicMock()
    user_repo.lock_tenant_users_for_status = AsyncMock()
    user_repo.unlock_tenant_users_for_status = AsyncMock()
    tenant_repo = MagicMock()
    tenant_repo.update = AsyncMock()
    tenant_repo.save_and_refresh = AsyncMock()
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=MagicMock(),
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


class TestUpdateTenantStatusAuthorization:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "target", [TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED]
    )
    async def test_tenant_admin_cannot_suspend_or_deactivate(
        self, target: TenantStatus
    ) -> None:
        svc = _tenant_service_with_mocks()
        tenant_admin = User(
            id=uuid4(),
            email="test-tenant-admin@example.invalid",
            username=uuid4().hex[:12],
            tenant_id=1,
        )
        svc._roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant_status(
                tenant_admin,
                1,
                _status_body(target),
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"
        svc._tenants.get_by_id_for_update.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "target", [TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED]
    )
    async def test_system_admin_can_suspend_or_deactivate(
        self, target: TenantStatus
    ) -> None:
        svc = _tenant_service_with_mocks()
        system_admin = User(
            id=uuid4(),
            email="test-system-admin@example.invalid",
            username=uuid4().hex[:12],
            tenant_id=1,
        )
        tenant = Tenant(
            id=1,
            name="Acme",
            organisation="Acme",
            email="test-contact@example.invalid",
            status=TenantStatus.ACTIVE,
        )
        svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        api_keys = AsyncMock()
        svc._api_keys = api_keys

        await svc.update_tenant_status(
            system_admin,
            1,
            _status_body(target),
        )

        svc._tenants.update.assert_awaited_once()
        svc._users.lock_tenant_users_for_status.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["status"] == target
        if target == TenantStatus.SUSPENDED:
            api_keys.evict_keys_for_tenant.assert_awaited_once_with(1)
            api_keys.revoke_keys_for_tenant.assert_not_awaited()
        else:
            api_keys.revoke_keys_for_tenant.assert_awaited_once_with(1)
            api_keys.evict_keys_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reactivate_suspended_refreshes_api_key_cache(self) -> None:
        svc = _tenant_service_with_mocks()
        system_admin = User(
            id=uuid4(),
            email="test-system-admin@example.invalid",
            username=uuid4().hex[:12],
            tenant_id=1,
        )
        tenant = Tenant(
            id=1,
            name="Acme",
            organisation="Acme",
            email="test-contact@example.invalid",
            status=TenantStatus.SUSPENDED,
        )
        svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        api_keys = AsyncMock()
        svc._api_keys = api_keys

        await svc.update_tenant_status(
            system_admin,
            1,
            _status_body(TenantStatus.ACTIVE),
        )

        api_keys.refresh_keys_cache_for_tenant.assert_awaited_once_with(1)
        api_keys.revoke_keys_for_tenant.assert_not_awaited()
        api_keys.evict_keys_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_activate_pending_tenant(self) -> None:
        """Status changes are admin-only (AI4IDS-1750): a tenant admin cannot
        activate even their own pending tenant via this endpoint."""
        svc = _tenant_service_with_mocks()
        tenant_admin = User(
            id=uuid4(),
            email="test-tenant-admin@example.invalid",
            username=uuid4().hex[:12],
            tenant_id=1,
        )
        svc._roles.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant_status(
                tenant_admin,
                1,
                _status_body(TenantStatus.ACTIVE),
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "INSUFFICIENT_PERMISSIONS"
        svc._tenants.get_by_id_for_update.assert_not_called()
        svc._tenants.update.assert_not_awaited()


def _default_tenant(status: TenantStatus = TenantStatus.ACTIVE) -> Tenant:
    return Tenant(
        id=1,
        name="Default Admin",
        organisation=settings.default_tenant_org.upper(),  # case-insensitivity
        email="test-default-contact@example.invalid",
        status=status,
    )


def _admin_user() -> User:
    return User(id=uuid4(), email="test-admin@example.invalid", username=uuid4().hex[:12])


def _tenant_user_body() -> User:
    return User(id=uuid4(), email="test-tenant-user@example.invalid", username=uuid4().hex[:12], tenant_id=1)


class TestDefaultTenantHelpers:
    def test_is_default_tenant_matches_case_insensitively(self) -> None:
        assert is_default_tenant(_default_tenant())

    def test_is_default_tenant_false_for_other_org(self) -> None:
        tenant = Tenant(id=2, name="Acme", organisation="Acme", email="test-acme@example.invalid")
        assert not is_default_tenant(tenant)

    def test_assert_default_tenant_not_targeted_raises_for_default_org(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            assert_default_tenant_not_targeted(_default_tenant())
        assert exc_info.value.code == "DEFAULT_ORG_PROTECTED"

    def test_assert_default_tenant_not_targeted_custom_message(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            assert_default_tenant_not_targeted(_default_tenant(), message="custom message")
        assert exc_info.value.code == "DEFAULT_ORG_PROTECTED"
        assert exc_info.value.message == "custom message"

    def test_assert_default_tenant_not_targeted_noop_for_other_org(self) -> None:
        tenant = Tenant(id=2, name="Acme", organisation="Acme", email="test-acme@example.invalid")
        assert_default_tenant_not_targeted(tenant)  # does not raise


class TestUpdateTenantStatusDefaultOrgGuard:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("target", [TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED])
    async def test_default_org_rejects_suspend_and_deactivate(self, target: TenantStatus) -> None:
        svc = _tenant_service_with_mocks()
        svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_default_tenant())

        with pytest.raises(ValidationError) as exc_info:
            await svc.update_tenant_status(_admin_user(), 1, _status_body(target))

        assert exc_info.value.code == "DEFAULT_ORG_PROTECTED"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_default_org_still_accepts_active(self) -> None:
        svc = _tenant_service_with_mocks()
        svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
        svc._tenants.get_by_id_for_update = AsyncMock(
            return_value=_default_tenant(status=TenantStatus.SUSPENDED)
        )
        svc._api_keys = AsyncMock()

        await svc.update_tenant_status(_admin_user(), 1, _status_body(TenantStatus.ACTIVE))

        svc._tenants.update.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["status"] == TenantStatus.ACTIVE


class TestUpdateTenantDefaultOrgRenameGuard:
    @pytest.mark.asyncio
    async def test_rejects_renaming_default_org(self) -> None:
        svc = _tenant_service_with_mocks()
        svc.enforce_scope = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        body = TenantUpdate(organisation="New Name For Default Org")

        with pytest.raises(ValidationError) as exc_info:
            await svc.update_tenant(_admin_user(), 1, body)

        assert exc_info.value.code == "DEFAULT_ORG_PROTECTED"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_allows_renaming_non_default_org(self) -> None:
        svc = _tenant_service_with_mocks()
        svc.enforce_scope = AsyncMock()
        tenant = Tenant(id=2, name="Acme", organisation="Acme", email="test-acme@example.invalid")
        svc._tenants.get_by_id = AsyncMock(return_value=tenant)
        svc._tenants.get_by_organisation = AsyncMock(return_value=None)
        svc._tenants.commit = AsyncMock()
        svc._tenants.refresh = AsyncMock()
        body = TenantUpdate(organisation="Acme Renamed")

        await svc.update_tenant(_admin_user(), 2, body)

        svc._tenants.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_allows_non_rename_update_on_default_org(self) -> None:
        svc = _tenant_service_with_mocks()
        svc.enforce_scope = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        svc._tenants.get_by_organisation = AsyncMock(return_value=None)
        svc._tenants.commit = AsyncMock()
        svc._tenants.refresh = AsyncMock()
        body = TenantUpdate(phone_number="+15550001111")

        await svc.update_tenant(_admin_user(), 1, body)

        svc._tenants.update.assert_awaited_once()


def _tenant_service_for_user_ops() -> TenantService:
    svc = _tenant_service_with_mocks()
    svc.enforce_scope = AsyncMock()
    svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
    return svc


class TestCreateTenantUserDefaultOrgGuard:
    @pytest.mark.asyncio
    async def test_rejects_tenant_admin_for_default_org(self) -> None:
        svc = _tenant_service_for_user_ops()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_default_tenant())
        svc.provision_user = AsyncMock()
        body = TenantUserCreate(
            email="new-tenant-admin@tenant.com",
            full_name="New Tenant Admin",
            role=TenantUserRole.TENANT_ADMIN,
        )

        with pytest.raises(ValidationError) as exc_info:
            await svc.create_tenant_user(_admin_user(), 1, body, MagicMock())

        assert exc_info.value.code == "DEFAULT_ORG_PROTECTED"
        svc.provision_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_plain_user_for_default_org(self) -> None:
        svc = _tenant_service_for_user_ops()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_default_tenant())
        svc.provision_user = AsyncMock(return_value=("user-id-123", "setup-token-abc"))
        body = TenantUserCreate(
            email="new-user@tenant.com",
            full_name="New User",
            role=TenantUserRole.USER,
        )

        with patch(
            "app.services.tenant_service.allocate_unique_username",
            new_callable=AsyncMock,
            return_value="newuser",
        ):
            result = await svc.create_tenant_user(_admin_user(), 1, body, MagicMock())

        assert result == ("user-id-123", "setup-token-abc")
        svc.provision_user.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_allows_tenant_admin_for_non_default_org(self) -> None:
        svc = _tenant_service_for_user_ops()
        tenant = Tenant(id=2, name="Acme", organisation="Acme", email="test-acme@example.invalid",
                         status=TenantStatus.ACTIVE)
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        svc.provision_user = AsyncMock(return_value=("user-id-456", "setup-token-def"))
        body = TenantUserCreate(
            email="new-tenant-admin@tenant.com",
            full_name="New Tenant Admin",
            role=TenantUserRole.TENANT_ADMIN,
        )

        with patch(
            "app.services.tenant_service.allocate_unique_username",
            new_callable=AsyncMock,
            return_value="newadmin",
        ):
            result = await svc.create_tenant_user(_admin_user(), 2, body, MagicMock())

        assert result == ("user-id-456", "setup-token-def")
        svc.provision_user.assert_awaited_once()


class TestUpdateTenantUserDefaultOrgGuard:
    @pytest.mark.asyncio
    async def test_rejects_promoting_to_tenant_admin_in_default_org(self) -> None:
        svc = _tenant_service_for_user_ops()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        target = _tenant_user_body()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        body = TenantUserUpdate(role=TenantUserRole.TENANT_ADMIN)

        with pytest.raises(ValidationError) as exc_info:
            await svc.update_tenant_user(_admin_user(), 1, target.id, body)

        assert exc_info.value.code == "DEFAULT_ORG_PROTECTED"
        svc._users.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_role_update_to_user_in_default_org(self) -> None:
        svc = _tenant_service_for_user_ops()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        target = _tenant_user_body()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.save_and_refresh = AsyncMock()
        svc._set_tenant_user_role = AsyncMock()
        body = TenantUserUpdate(role=TenantUserRole.USER)

        await svc.update_tenant_user(_admin_user(), 1, target.id, body)

        svc._users.update.assert_awaited_once()
        svc._set_tenant_user_role.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_allows_non_role_update_in_default_org(self) -> None:
        svc = _tenant_service_for_user_ops()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        target = _tenant_user_body()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.save_and_refresh = AsyncMock()
        body = TenantUserUpdate(full_name="Renamed Default User")

        await svc.update_tenant_user(_admin_user(), 1, target.id, body)

        svc._users.update.assert_awaited_once()


class TestAssertTenantAdminAssignable:
    """Backs the /auth/roles/assign guard: same DEFAULT_ORG_PROTECTED policy."""

    @pytest.mark.asyncio
    async def test_rejects_default_org(self) -> None:
        tenant_repo = AsyncMock()
        tenant_repo.get_by_id = AsyncMock(return_value=_default_tenant())

        with pytest.raises(ValidationError) as exc_info:
            await assert_tenant_admin_assignable(tenant_repo, 1)

        assert exc_info.value.code == "DEFAULT_ORG_PROTECTED"

    @pytest.mark.asyncio
    async def test_allows_non_default_org(self) -> None:
        tenant_repo = AsyncMock()
        tenant_repo.get_by_id = AsyncMock(
            return_value=Tenant(id=2, name="Acme", organisation="Acme", email="test-acme@example.invalid")
        )

        await assert_tenant_admin_assignable(tenant_repo, 2)  # does not raise

    @pytest.mark.asyncio
    async def test_noop_when_tenant_id_is_none(self) -> None:
        tenant_repo = AsyncMock()

        await assert_tenant_admin_assignable(tenant_repo, None)  # does not raise

        tenant_repo.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_closed_when_tenant_row_missing(self) -> None:
        """A stale/orphaned tenant_id must reject rather than let the assignment through."""
        tenant_repo = AsyncMock()
        tenant_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(EntityNotFoundError):
            await assert_tenant_admin_assignable(tenant_repo, 999)
