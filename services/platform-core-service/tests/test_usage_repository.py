"""Unit tests for UsageRepository.get_tier_names()'s in-process TTL cache,
and for the get_tenant_budgets lookup-instant selection.

The cache lives at module scope (app.repositories.pay_per_use.usage_repository),
not on the instance, since UsageRepository is constructed fresh per request. That
means state can leak between test functions unless it's reset — hence the autouse
fixture below.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.pay_per_use import usage_repository as repo_module
from app.repositories.pay_per_use.usage_repository import (
    UsageRepository,
    _budget_lookup_instant,
    _end_of_month,
)


@pytest.fixture(autouse=True)
def _reset_tier_cache():
    """Ensure each test starts from a cold cache and leaves none behind."""
    repo_module._tier_cache = {}
    repo_module._tier_cache_loaded_at = None
    yield
    repo_module._tier_cache = {}
    repo_module._tier_cache_loaded_at = None


def _make_db(rows: list[SimpleNamespace]) -> AsyncMock:
    """Fake AsyncSession whose execute() returns rows shaped like the
    (Tier.id, Tier.name) tuples get_tier_names() selects."""
    db = AsyncMock()
    result = SimpleNamespace(all=lambda: rows)
    db.execute = AsyncMock(return_value=result)
    return db


def _freeze_now(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    """Pin repo_module's datetime.now() so _budget_lookup_instant is deterministic."""

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(repo_module, "datetime", _FrozenDateTime)


class TestBudgetLookupInstant:
    """_budget_lookup_instant picks "now" for the current billing_month (so a
    just-topped-up assignment that hasn't reached the calendar month's end is
    still found) and _end_of_month for any past billing_month (a closed month
    gets a stable, frozen snapshot instead of drifting with wall-clock time)."""

    def test_current_month_uses_now(self, monkeypatch):
        now = datetime(2026, 7, 21, 9, 52, 37, tzinfo=timezone.utc)
        _freeze_now(monkeypatch, now)

        assert _budget_lookup_instant("2026-07") == now

    def test_past_month_uses_end_of_month(self, monkeypatch):
        now = datetime(2026, 7, 21, 9, 52, 37, tzinfo=timezone.utc)
        _freeze_now(monkeypatch, now)

        assert _budget_lookup_instant("2026-06") == _end_of_month("2026-06")

    def test_current_month_instant_falls_inside_assignment_ending_at_midnight(
        self, monkeypatch
    ):
        """Regression: an assignment valid through "2026-07-31T00:00:00Z" (the
        shape reassign_tier/revise_budget actually write) never reaches
        _end_of_month("2026-07")'s 23:59:59.999999 instant, which is why a
        freshly topped-up tenant's budget was reading back as 0. Comparing
        against "now" instead — while July is still the current month — fixes
        that without needing effective_to's shape to change at all."""
        now = datetime(2026, 7, 21, 9, 52, 37, tzinfo=timezone.utc)
        _freeze_now(monkeypatch, now)
        effective_from = datetime(2026, 7, 21, 9, 52, 37, tzinfo=timezone.utc)
        effective_to = datetime(2026, 7, 31, 0, 0, 0, tzinfo=timezone.utc)

        lookup_instant = _budget_lookup_instant("2026-07")

        assert effective_from <= lookup_instant < effective_to


class TestBillingMonthOmitted:
    """billing_month=None means all-time (usage up to now) — the query must drop the
    billing_month equality filter entirely rather than defaulting to any one month.
    Captures the compiled statement passed to db.execute() and inspects its WHERE
    clause, since these two methods build the SQL directly (no repo method to mock)."""

    @staticmethod
    def _capturing_db(rows: list = ()) -> tuple[AsyncMock, list]:
        captured: list = []
        result = SimpleNamespace(all=lambda: list(rows))

        async def _execute(stmt, *args, **kwargs):
            captured.append(stmt)
            return result

        db = AsyncMock()
        db.execute = _execute
        return db, captured

    @pytest.mark.asyncio
    async def test_get_tenants_with_usage_tier_omits_billing_month_filter(self):
        db, captured = self._capturing_db()
        repo = UsageRepository(db=db)

        await repo.get_tenants_with_usage_tier(None)

        compiled = str(captured[0])
        assert "billing_month" not in compiled

    @pytest.mark.asyncio
    async def test_get_tenants_with_usage_tier_keeps_filter_when_given(self):
        db, captured = self._capturing_db()
        repo = UsageRepository(db=db)

        await repo.get_tenants_with_usage_tier("2026-06")

        compiled = str(captured[0])
        assert "billing_month" in compiled

    @pytest.mark.asyncio
    async def test_get_tenant_tier_usage_breakdown_omits_billing_month_filter(self):
        db, captured = self._capturing_db()
        repo = UsageRepository(db=db)

        await repo.get_tenant_tier_usage_breakdown(None, ["t1"])

        compiled = str(captured[0])
        assert "billing_month" not in compiled

    @pytest.mark.asyncio
    async def test_get_tenant_tier_usage_breakdown_keeps_filter_when_given(self):
        db, captured = self._capturing_db()
        repo = UsageRepository(db=db)

        await repo.get_tenant_tier_usage_breakdown("2026-06", ["t1"])

        compiled = str(captured[0])
        assert "billing_month" in compiled


class TestGetTenantBudgets:
    """Exact-bug-scenario regression test: ppu_tenant_tier_assignments was
    dropped (AI4IDS-2923); get_tenant_budgets previously queried it directly
    and raised UndefinedTableError in production (reproduced live against
    /usage-summary, /usage-tenants, /usage-tenant). Reconstructed from
    tenants.allocated_budget + budget_usage (via api_key/applications), so
    these tests exercise the actual cross-DB query logic, not a mocked
    repository interface.
    """

    @staticmethod
    def _auth_db(side_effects: list) -> MagicMock:
        auth_db = MagicMock()
        auth_db.execute = AsyncMock(side_effect=side_effects)
        return auth_db

    @staticmethod
    def _rows(rows: list) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: rows)

    @pytest.mark.asyncio
    async def test_empty_tenant_ids_returns_empty_without_querying(self):
        repo = UsageRepository(db=AsyncMock())
        auth_db = self._auth_db([])

        result = await repo.get_tenant_budgets("2026-08", [], auth_db)

        assert result == {}
        auth_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_auth_db_none_returns_empty(self):
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-08", ["2"], None)

        assert result == {}

    @pytest.mark.asyncio
    async def test_normal_case_computes_budget_from_allocated_minus_spend(self):
        auth_db = self._auth_db(
            [
                self._rows(
                    [SimpleNamespace(
                        id=2, allocated_budget=Decimal("1000000.00"), tier_id=None,
                        budget_effective_from=None, budget_effective_to=None,
                    )]
                ),  # tenants
                self._rows(
                    [SimpleNamespace(id=39, tenant_id=2), SimpleNamespace(id=40, tenant_id=2)]
                ),  # applications
                self._rows(
                    [
                        SimpleNamespace(id=10, application_id=39),
                        SimpleNamespace(id=11, application_id=39),
                        SimpleNamespace(id=12, application_id=40),
                    ]
                ),  # api_key
            ]
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=self._rows(
                [
                    SimpleNamespace(api_key_id=10, api_key_budget_used=Decimal("70000.00")),
                    SimpleNamespace(api_key_id=11, api_key_budget_used=Decimal("30000.00")),
                    SimpleNamespace(api_key_id=12, api_key_budget_used=Decimal("90000.00")),
                ]
            )
        )
        repo = UsageRepository(db=db)

        result = await repo.get_tenant_budgets("2026-08", ["2"], auth_db)

        assert set(result.keys()) == {"2"}
        budget = result["2"]
        assert budget.budget_limit == Decimal("1000000.00")
        assert budget.available_balance == Decimal("810000.00")  # 1,000,000 - (70000+30000+90000)
        # The real, tenant-total spend: the sum of api_key_budget_used across every
        # api_key belonging to one of the tenant's applications (2 applications, 3
        # api_keys total, spanning both) — the exact "spend for a tenant is the sum
        # of its api keys' spend" scenario this field exists for.
        assert budget.spent == Decimal("190000.00")  # 70000 + 30000 + 90000
        assert budget.tier_id is None

    @pytest.mark.asyncio
    async def test_budget_effective_from_and_to_are_read_through(self):
        """budget_effective_from/to come straight off tenants.budget_effective_from/to
        (auth-service) — set once at tenant creation, untouched by top-up/top-down —
        and must be carried onto the returned SimpleNamespace as-is, not dropped or
        defaulted, so get_tenant_detail's TenantBudgetDetail can surface them."""
        effective_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        effective_to = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        auth_db = self._auth_db(
            [
                self._rows(
                    [SimpleNamespace(
                        id=2, allocated_budget=Decimal("1000.00"), tier_id=None,
                        budget_effective_from=effective_from, budget_effective_to=effective_to,
                    )]
                ),  # tenants
                self._rows([]),  # applications — none
            ]
        )
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-08", ["2"], auth_db)

        assert result["2"].budget_effective_from == effective_from
        assert result["2"].budget_effective_to == effective_to

    @pytest.mark.asyncio
    async def test_tenant_not_in_auth_db_is_absent_from_result(self):
        auth_db = self._auth_db([self._rows([])])  # tenants query returns nothing

        repo = UsageRepository(db=AsyncMock())
        result = await repo.get_tenant_budgets("2026-08", ["999"], auth_db)

        assert result == {}

    @pytest.mark.asyncio
    async def test_tenant_with_no_applications_has_zero_spend(self):
        auth_db = self._auth_db(
            [
                self._rows(
                    [SimpleNamespace(
                        id=5, allocated_budget=Decimal("50000.00"), tier_id=None,
                        budget_effective_from=None, budget_effective_to=None,
                    )]
                ),  # tenants
                self._rows([]),  # applications — none
            ]
        )
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-08", ["5"], auth_db)

        budget = result["5"]
        assert budget.budget_limit == Decimal("50000.00")
        assert budget.available_balance == Decimal("50000.00")

    @pytest.mark.asyncio
    async def test_non_digit_tenant_id_short_circuits_without_querying(self):
        auth_db = self._auth_db([])
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-08", ["not-a-number"], auth_db)

        assert result == {}
        auth_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_tenant_with_null_allocated_budget_is_absent_from_result(self):
        """Regression: a tenant that EXISTS in auth-service's tenants table but has
        never had a budget configured (allocated_budget IS NULL — the column is
        nullable, and optional on tenant create/update) must be excluded from the
        returned dict, not coalesced to budget_limit=0. Coalescing to 0 would make
        _resolve_budget report has_budget=True with a limit of 0, so get_summary
        would count this tenant's any-nonzero-spend as "budget exceeded" purely
        because no budget was ever set — the exact "unknown vs. genuinely zero"
        mixup this module's docstring says must not happen."""
        auth_db = self._auth_db(
            [
                self._rows(
                    [SimpleNamespace(id=42, allocated_budget=None, tier_id=None)]
                ),  # tenants — exists, but no budget on file
                self._rows(
                    [SimpleNamespace(id=39, tenant_id=42)]
                ),  # applications
                self._rows(
                    [SimpleNamespace(id=10, application_id=39)]
                ),  # api_key
            ]
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=self._rows(
                [SimpleNamespace(api_key_id=10, api_key_budget_used=Decimal("150.00"))]
            )
        )
        repo = UsageRepository(db=db)

        result = await repo.get_tenant_budgets("2026-08", ["42"], auth_db)

        assert result == {}

    @pytest.mark.asyncio
    async def test_mixed_null_and_real_budgets_only_excludes_the_null_one(self):
        """Same lookup batch, one tenant with a real budget and one with none on
        file — only the NULL one should be dropped; the other must still resolve
        normally with its own spend correctly attributed (not merged/lost)."""
        auth_db = self._auth_db(
            [
                self._rows(
                    [
                        SimpleNamespace(
                            id=2, allocated_budget=Decimal("1000.00"), tier_id=None,
                            budget_effective_from=None, budget_effective_to=None,
                        ),
                        SimpleNamespace(
                            id=42, allocated_budget=None, tier_id=None,
                            budget_effective_from=None, budget_effective_to=None,
                        ),
                    ]
                ),  # tenants
                self._rows(
                    [
                        SimpleNamespace(id=39, tenant_id=2),
                        SimpleNamespace(id=40, tenant_id=42),
                    ]
                ),  # applications
                self._rows(
                    [
                        SimpleNamespace(id=10, application_id=39),
                        SimpleNamespace(id=11, application_id=40),
                    ]
                ),  # api_key
            ]
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=self._rows(
                [
                    SimpleNamespace(api_key_id=10, api_key_budget_used=Decimal("300.00")),
                    SimpleNamespace(api_key_id=11, api_key_budget_used=Decimal("150.00")),
                ]
            )
        )
        repo = UsageRepository(db=db)

        result = await repo.get_tenant_budgets("2026-08", ["2", "42"], auth_db)

        assert set(result.keys()) == {"2"}
        assert result["2"].budget_limit == Decimal("1000.00")
        assert result["2"].available_balance == Decimal("700.00")

    @pytest.mark.asyncio
    async def test_auth_db_failure_propagates_instead_of_degrading_to_empty(self):
        """Regression: a real auth_db failure (connection drop, aborted
        transaction) must NOT be swallowed into `{}` — that made _resolve_budget
        report has_budget=False for every tenant, so /usage-summary answered
        200 OK with totalAllocatedBudget=0 during an actual outage, exactly the
        false zero application_usage_service._load_tenant_budget already
        refuses to produce (see its docstring). The caller-side route/global
        exception handler is what turns this into a 500 — this repository
        method's job is only to not hide it."""
        auth_db = MagicMock()
        auth_db.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
        repo = UsageRepository(db=AsyncMock())

        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_tenant_budgets("2026-08", ["2"], auth_db)

    @pytest.mark.asyncio
    async def test_auth_db_failure_mid_sequence_also_propagates(self):
        """The tenants query can succeed and the transaction still abort on the
        very next statement (applications query) — a realistic partial-failure
        shape, not just a first-call failure. Must propagate exactly the same
        as a failure on the first query, not be masked by having already
        fetched some rows."""
        auth_db = self._auth_db(
            [
                self._rows(
                    [SimpleNamespace(id=2, allocated_budget=Decimal("1000.00"), tier_id=None)]
                ),  # tenants — succeeds
                RuntimeError("transaction aborted"),  # applications — fails
            ]
        )
        repo = UsageRepository(db=AsyncMock())

        with pytest.raises(RuntimeError, match="transaction aborted"):
            await repo.get_tenant_budgets("2026-08", ["2"], auth_db)
