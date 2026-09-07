"""Unit tests for ApplicationUsageRepository.get_spend_by_api_key_ids()."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.pay_per_use.application_usage_repository import (
    ApplicationUsageRepository,
)


def _make_db(rows: list[SimpleNamespace]) -> AsyncMock:
    db = AsyncMock()
    result = SimpleNamespace(all=lambda: rows)
    db.execute = AsyncMock(return_value=result)
    return db


class TestGetSpendByApiKeyIds:
    @pytest.mark.asyncio
    async def test_empty_ids_short_circuits_without_querying(self):
        db = _make_db([])
        repo = ApplicationUsageRepository(db)

        result = await repo.get_spend_by_api_key_ids([])

        assert result == {}
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_maps_rows_to_spend_by_key_id(self):
        rows = [
            SimpleNamespace(api_key_id=1, api_key_budget_used=Decimal("70000.00")),
            SimpleNamespace(api_key_id=2, api_key_budget_used=Decimal("30000.00")),
        ]
        db = _make_db(rows)
        repo = ApplicationUsageRepository(db)

        result = await repo.get_spend_by_api_key_ids([1, 2, 3])

        assert result == {1: Decimal("70000.00"), 2: Decimal("30000.00")}

    @pytest.mark.asyncio
    async def test_null_budget_used_defaults_to_zero(self):
        rows = [SimpleNamespace(api_key_id=1, api_key_budget_used=None)]
        db = _make_db(rows)
        repo = ApplicationUsageRepository(db)

        result = await repo.get_spend_by_api_key_ids([1])

        assert result == {1: Decimal("0")}

    @pytest.mark.asyncio
    async def test_key_with_no_row_is_simply_absent(self):
        db = _make_db([])
        repo = ApplicationUsageRepository(db)

        result = await repo.get_spend_by_api_key_ids([99])

        assert result == {}
