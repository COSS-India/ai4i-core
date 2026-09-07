"""app.services.budget_usage — the cross-DB budget_usage read/write helpers.

Every other test in this suite that touches allocations (test_allocation_service.py)
patches these two functions out entirely, so the actual SQL they build — the
upsert's ON CONFLICT clause in particular, the one genuinely new persistence
path this feature adds — had no coverage anywhere. These tests exercise the
real functions against a mocked AsyncSession, asserting on what SQL and
params actually get sent, not just that "something" was called.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.budget_usage import fetch_budget_usage, write_budget_snapshot


def _row(api_key_id: int, used, snap):
    row = MagicMock()
    row.api_key_id = api_key_id
    row.api_key_budget_used = used
    row.api_key_budget_snap = snap
    return row


class TestFetchBudgetUsage:
    @pytest.mark.asyncio
    async def test_empty_key_ids_short_circuits_without_querying(self) -> None:
        db = AsyncMock()
        result = await fetch_budget_usage([], db)
        assert result == {}
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_none_db_short_circuits_without_querying(self) -> None:
        result = await fetch_budget_usage([1, 2], None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_used_and_snap_keyed_by_api_key_id(self) -> None:
        db = AsyncMock()
        result_obj = MagicMock()
        result_obj.all.return_value = [
            _row(1, Decimal("4000"), Decimal("5000")),
            _row(2, Decimal("0"), Decimal("2000")),
        ]
        db.execute = AsyncMock(return_value=result_obj)

        result = await fetch_budget_usage([1, 2, 3], db)

        assert result == {
            1: (Decimal("4000"), Decimal("5000")),
            2: (Decimal("0"), Decimal("2000")),
        }
        # Key 3 (no row) is simply absent — callers treat that as used=0.
        assert 3 not in result

        # Sent the right ids, against the right table.
        args, kwargs = db.execute.await_args.args, db.execute.await_args.kwargs
        sql_text = str(args[0])
        assert "budget_usage" in sql_text
        assert "api_key_id" in sql_text
        params = args[1] if len(args) > 1 else kwargs.get("parameters")
        assert params == {"key_ids": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_db_error_returns_empty_dict_rather_than_raising(self) -> None:
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("connection reset"))
        result = await fetch_budget_usage([1], db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_raise_on_error_propagates_the_failure(self) -> None:
        """raise_on_error=True is for callers (tenant_service's
        _sync_ppu_wallet_and_exhaustion) that cannot treat {} as "zero
        spend" on failure, since that reads identically to "zero rows,
        query succeeded" and would let them write a wrong derived value."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("connection reset"))
        with pytest.raises(RuntimeError, match="connection reset"):
            await fetch_budget_usage([1], db, raise_on_error=True)

    @pytest.mark.asyncio
    async def test_raise_on_error_still_short_circuits_on_empty_key_ids(self) -> None:
        # Not a failure case — must stay {} even with raise_on_error=True.
        db = AsyncMock()
        result = await fetch_budget_usage([], db, raise_on_error=True)
        assert result == {}
        db.execute.assert_not_awaited()


class TestWriteBudgetSnapshot:
    @pytest.mark.asyncio
    async def test_empty_snapshots_short_circuits_without_writing(self) -> None:
        db = AsyncMock()
        await write_budget_snapshot({}, db)
        db.execute.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_none_db_short_circuits_without_writing(self) -> None:
        # Must not raise even though there's nothing to write to.
        await write_budget_snapshot({1: Decimal("1000")}, None)

    @pytest.mark.asyncio
    async def test_upserts_one_statement_per_key_and_commits_once(self) -> None:
        db = AsyncMock()
        snapshots = {1: Decimal("40000.00"), 2: Decimal("16000.00")}

        await write_budget_snapshot(snapshots, db)

        assert db.execute.await_count == 2
        sent_params = [call.args[1] for call in db.execute.await_args_list]
        assert {"api_key_id": 1, "snap": Decimal("40000.00")} in sent_params
        assert {"api_key_id": 2, "snap": Decimal("16000.00")} in sent_params
        db.commit.assert_awaited_once()
        db.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sql_upserts_on_conflict_api_key_id_and_touches_only_the_snapshot(self) -> None:
        """The one thing this write must never do: touch api_key_budget_used
        on conflict — that's a different writer's running total, not this
        call's business."""
        db = AsyncMock()
        await write_budget_snapshot({1: Decimal("1000")}, db)

        sql_text = str(db.execute.await_args.args[0])
        assert "INSERT INTO budget_usage" in sql_text
        assert "ON CONFLICT (api_key_id)" in sql_text
        assert "DO UPDATE SET api_key_budget_snap = EXCLUDED.api_key_budget_snap" in sql_text
        assert "api_key_budget_used" not in sql_text.split("DO UPDATE")[1]

    @pytest.mark.asyncio
    async def test_db_error_rolls_back_rather_than_raising(self) -> None:
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("connection reset"))

        # Best-effort: must not raise, must not block the caller's own
        # allocation write that this mirrors.
        await write_budget_snapshot({1: Decimal("1000")}, db)

        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()
