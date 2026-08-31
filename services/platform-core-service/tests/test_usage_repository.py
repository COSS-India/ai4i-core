"""Unit tests for UsageRepository.get_tenant_budgets().

ppu_tenant_tier_assignments (the only table this method ever read) has been
dropped — there is no replacement budget-per-tenant data source in
this service's own DB (budget_usage has no tenant_id column, only
api_key_id). get_tenant_budgets now always returns {}; this pins that
contract so it isn't accidentally reverted to querying the dropped table
again (which raises "relation does not exist", not a graceful empty
result — see UsageRepository.get_tenant_budgets's own docstring).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.repositories.pay_per_use.usage_repository import UsageRepository


class TestGetTenantBudgets:
    @pytest.mark.asyncio
    async def test_always_returns_empty_dict(self):
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-06", ["t1", "t2"])

        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_tenant_ids_also_returns_empty_dict(self):
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-06", [])

        assert result == {}

    @pytest.mark.asyncio
    async def test_does_not_touch_the_db(self):
        """No query is issued at all — a live DB call here would mean the
        dropped-table query crept back in."""
        db = AsyncMock()
        repo = UsageRepository(db=db)

        await repo.get_tenant_budgets("2026-06", ["t1"])

        db.execute.assert_not_called()
