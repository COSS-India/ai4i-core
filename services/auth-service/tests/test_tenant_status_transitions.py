"""Tenant status transition rules and user-flag sync."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import ValidationError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_lifecycle import (
    assert_valid_tenant_status_transition,
    sync_tenant_users_for_status,
)
from app.services.tenant_service import (
    TenantService,
    _assert_tenant_active_for_user_deactivation,
    _payload_touches_user_access,
)


class TestTenantStatusTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (TenantStatus.PENDING, TenantStatus.ACTIVE),
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
            (TenantStatus.PENDING, TenantStatus.DEACTIVATED),
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
    def test_payload_touches_user_access(self) -> None:
        assert _payload_touches_user_access({"is_active": False}) is True
        assert _payload_touches_user_access({"is_tenant_active": True}) is True
        assert _payload_touches_user_access({"updated_by": uuid4()}) is False

    def test_deactivate_user_requires_active_tenant(self) -> None:
        tenant = Tenant(id=1, status=TenantStatus.SUSPENDED)
        with pytest.raises(ValidationError) as exc_info:
            _assert_tenant_active_for_user_deactivation(tenant, {"is_active": False})
        assert exc_info.value.code == "TENANT_NOT_ACTIVE"

    def test_revoke_tenant_access_only_skips_tenant_active_check(self) -> None:
        tenant = Tenant(id=1, status=TenantStatus.SUSPENDED)
        _assert_tenant_active_for_user_deactivation(
            tenant, {"is_active": True, "is_tenant_active": False}
        )

    def test_reactivate_tenant_access_only_skips_tenant_active_check(self) -> None:
        tenant = Tenant(id=1, status=TenantStatus.SUSPENDED)
        _assert_tenant_active_for_user_deactivation(tenant, {"is_tenant_active": True})


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
            email="admin@example.com",
            username="tenant_admin",
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
            email="sys@example.com",
            username="sys_admin",
            tenant_id=1,
        )
        tenant = Tenant(
            id=1,
            name="Acme",
            organisation="Acme",
            email="contact@acme.com",
            status=TenantStatus.ACTIVE,
        )
        svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)

        await svc.update_tenant_status(
            system_admin,
            1,
            _status_body(target),
        )

        svc._tenants.update.assert_awaited_once()
        svc._users.lock_tenant_users_for_status.assert_awaited_once()
        assert svc._tenants.update.await_args.args[1]["status"] == target

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_activate_pending_tenant(self) -> None:
        """Status changes are admin-only (AI4IDS-1750): a tenant admin cannot
        activate even their own pending tenant via this endpoint."""
        svc = _tenant_service_with_mocks()
        tenant_admin = User(
            id=uuid4(),
            email="admin@example.com",
            username="tenant_admin",
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
