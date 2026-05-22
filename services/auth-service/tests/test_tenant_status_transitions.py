"""Tenant status transition rules and user-flag sync."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.tenant import TenantStatus
from app.services.tenant_service import (
    assert_valid_tenant_status_transition,
    sync_tenant_users_for_status,
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
