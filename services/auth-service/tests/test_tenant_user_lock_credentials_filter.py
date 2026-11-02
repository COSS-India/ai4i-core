"""Tenant-lock cascade must skip pending-activation (never-activated) users.

When a tenant is SUSPENDED/DEACTIVATED, only users who have been activated
(``activated_at`` set) should get ``is_tenant_active=False``. A credentials row
is not the test: a self-signup has one before verifying its email. Pending-activation
users never had an active account, so marking them Suspended is semantically
wrong and could strand them on reactivation. Reactivation still restores access
for every user.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.repositories.user_repository import UserRepository


def _sql(stmt) -> str:
    return str(stmt).lower()


class TestLockTenantUsersForStatus:
    @pytest.mark.asyncio
    async def test_lock_only_targets_activated_users(self) -> None:
        db = AsyncMock()
        repo = UserRepository(db)

        await repo.lock_tenant_users_for_status(7, updated_by=uuid4())

        db.execute.assert_awaited_once()
        sql = _sql(db.execute.await_args.args[0])
        # activated_at excludes never-activated users, including self-signups
        # that already hold credentials while waiting on email verification.
        assert "users.activated_at is not null" in sql
        assert "user_credentials" not in sql

    @pytest.mark.asyncio
    async def test_unlock_restores_every_user(self) -> None:
        db = AsyncMock()
        repo = UserRepository(db)

        await repo.unlock_tenant_users_for_status(7, updated_by=uuid4())

        db.execute.assert_awaited_once()
        sql = _sql(db.execute.await_args.args[0])
        # Reactivation is unconditional: no activation filter, restore all users.
        assert "activated_at" not in sql
