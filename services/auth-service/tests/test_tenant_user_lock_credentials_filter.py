"""Tenant-lock cascade must skip pending-activation (never-activated) users.

When a tenant is SUSPENDED/DEACTIVATED, only users who completed setup (a
credentials row exists) should get ``is_tenant_active=False``. Pending-activation
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
    async def test_lock_only_targets_users_with_credentials(self) -> None:
        db = AsyncMock()
        repo = UserRepository(db)

        await repo.lock_tenant_users_for_status(7, updated_by=uuid4())

        db.execute.assert_awaited_once()
        sql = _sql(db.execute.await_args.args[0])
        # Correlated EXISTS against user_credentials excludes never-activated users.
        assert "user_credentials" in sql
        assert "exists" in sql

    @pytest.mark.asyncio
    async def test_unlock_restores_every_user(self) -> None:
        db = AsyncMock()
        repo = UserRepository(db)

        await repo.unlock_tenant_users_for_status(7, updated_by=uuid4())

        db.execute.assert_awaited_once()
        sql = _sql(db.execute.await_args.args[0])
        # Reactivation is unconditional: no credentials filter, restore all users.
        assert "user_credentials" not in sql
