"""Unit tests for ApplicationUsageService — percentage math and edge cases.

Mirrors test_usage_service.py's style: the repository/auth_db boundary is
mocked, no real DB or FastAPI TestClient involved.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import EntityNotFoundError
from app.services.pay_per_use.application_usage_service import ApplicationUsageService


class _Row:
    """Fake SQLAlchemy Row exposing ._mapping, like the real thing does."""

    def __init__(self, **kwargs):
        self._mapping = kwargs


def _make_auth_db(execute_results: list) -> MagicMock:
    auth_db = MagicMock()
    auth_db.execute = AsyncMock(side_effect=execute_results)
    return auth_db


def _budget_result(amount):
    return SimpleNamespace(first=lambda: (amount,) if amount is not None else None)


def _rows_result(rows: list):
    return SimpleNamespace(all=lambda: rows)


def _make_repo(spend_by_key: dict) -> MagicMock:
    repo = MagicMock()
    repo.get_spend_by_api_key_ids = AsyncMock(return_value=spend_by_key)
    return repo


class TestTenantIdIntegerCasting:
    """Regression test for a real bug caught by live-DB testing (mocks don't
    enforce parameter types, so this was invisible to every other test here).

    tenants.id / applications.tenant_id are Postgres Integer columns.
    tenant_id arrives as a str everywhere in this service (X-Tenant-Id header,
    FastAPI Query str param). asyncpg — unlike psycopg2 — refuses to bind a
    Python str against an Integer column, raising:
      asyncpg.exceptions.DataError: invalid input for query argument $1: '2'
      ('str' object cannot be interpreted as an integer)
    This fake execute() reproduces that exact refusal so the regression is
    caught without needing a live database.
    """

    @staticmethod
    def _capturing_execute(captured: dict) -> AsyncMock:
        """Records the actual bound params instead of just returning canned
        rows — asserting on THIS is what actually distinguishes fixed from
        buggy: the service's own `except Exception` swallows a real asyncpg
        DataError and returns a graceful zero either way, so asserting only
        on the method's return value passes even with the bug still present.
        """
        async def _execute(stmt, params=None):
            captured.update(params or {})
            return SimpleNamespace(all=lambda: [], first=lambda: None)

        return AsyncMock(side_effect=_execute)

    @pytest.mark.asyncio
    async def test_load_tenant_budget_binds_int_not_str(self):
        captured: dict = {}
        auth_db = MagicMock()
        auth_db.execute = self._capturing_execute(captured)

        # The exact failing scenario: tenant_id="2" arrives as a str (from
        # X-Tenant-Id/Query) and must be cast before binding — asyncpg
        # rejects a str for an Integer column outright.
        await ApplicationUsageService._load_tenant_budget("2", auth_db)

        assert captured["tenant_id"] == 2
        assert isinstance(captured["tenant_id"], int)

    @pytest.mark.asyncio
    async def test_load_tenant_applications_binds_int_not_str(self):
        captured: dict = {}
        auth_db = MagicMock()
        auth_db.execute = self._capturing_execute(captured)

        await ApplicationUsageService._load_tenant_applications("2", auth_db)

        assert captured["tenant_id"] == 2
        assert isinstance(captured["tenant_id"], int)

    @pytest.mark.asyncio
    async def test_non_digit_tenant_id_short_circuits_without_querying(self):
        """A malformed tenant_id (not a digit string) must never reach the
        database at all — not even as a query that could raise or, worse,
        silently match the wrong row under a permissive driver."""
        auth_db = MagicMock()
        auth_db.execute = AsyncMock()

        budget = await ApplicationUsageService._load_tenant_budget("not-a-number", auth_db)
        apps = await ApplicationUsageService._load_tenant_applications("not-a-number", auth_db)

        assert budget == Decimal("0")
        assert apps == []
        auth_db.execute.assert_not_called()


class TestGetSummary:
    @pytest.mark.asyncio
    async def test_normal_case_computes_institution_level_percentages(self):
        auth_db = _make_auth_db(
            [
                _budget_result(Decimal("1000000.00")),  # tenant budget
                _rows_result(
                    [
                        _Row(id=1, name="Citizen Services", domain="cs.gov", allocated_percentage=Decimal("40.00"), allocated_budget=Decimal("400000.00"), status="ACTIVE"),
                        _Row(id=2, name="Grievance Redressal", domain=None, allocated_percentage=Decimal("20.00"), allocated_budget=Decimal("200000.00"), status="ACTIVE"),
                    ]
                ),  # applications
                _rows_result(
                    [
                        _Row(id=10, application_id=1, key_name="Web", api_key="a" * 28 + "a91d", allocated_percentage=Decimal("24.00"), allocated_budget=Decimal("240000.00"), is_active=True),
                        _Row(id=11, application_id=2, key_name="Batch", api_key="b" * 28 + "44f2", allocated_percentage=Decimal("16.00"), allocated_budget=Decimal("160000.00"), is_active=True),
                    ]
                ),  # api keys
            ]
        )
        repo = _make_repo({10: Decimal("70000.00"), 11: Decimal("30000.00")})
        svc = ApplicationUsageService(repo)

        result = await svc.get_summary("1", auth_db)

        assert result.totalApplications == 2
        assert result.allocatedBudget.amount == 600000.0
        assert result.allocatedBudget.percentage == 60.0
        assert result.spendBudget.amount == 100000.0
        assert result.spendBudget.percentage == 10.0
        assert result.remainingBudget.amount == 500000.0
        assert result.remainingBudget.percentage == 50.0

    @pytest.mark.asyncio
    async def test_tenant_with_zero_applications(self):
        auth_db = _make_auth_db(
            [_budget_result(Decimal("1000000.00")), _rows_result([])]
        )
        repo = _make_repo({})
        svc = ApplicationUsageService(repo)

        result = await svc.get_summary("1", auth_db)

        assert result.totalApplications == 0
        assert result.allocatedBudget.amount == 0.0
        assert result.allocatedBudget.percentage == 0.0

    @pytest.mark.asyncio
    async def test_auth_db_none_returns_zeroed_summary_without_error(self):
        repo = _make_repo({})
        svc = ApplicationUsageService(repo)

        result = await svc.get_summary("1", None)

        assert result.totalApplications == 0
        assert result.allocatedBudget.amount == 0.0


class TestGetApplicationList:
    @pytest.mark.asyncio
    async def test_sorts_by_spend_and_computes_own_allocation_percentages(self):
        auth_db = _make_auth_db(
            [
                _budget_result(Decimal("1000000.00")),
                _rows_result(
                    [
                        _Row(id=1, name="App A", domain=None, allocated_percentage=Decimal("40.00"), allocated_budget=Decimal("400000.00"), status="ACTIVE"),
                        _Row(id=2, name="App B", domain=None, allocated_percentage=Decimal("20.00"), allocated_budget=Decimal("200000.00"), status="ACTIVE"),
                    ]
                ),
                _rows_result(
                    [
                        _Row(id=10, application_id=1, key_name="k1", api_key="x1d", allocated_percentage=Decimal("100.00"), allocated_budget=Decimal("400000.00"), is_active=True),
                        _Row(id=11, application_id=2, key_name="k2", api_key="x2d", allocated_percentage=Decimal("100.00"), allocated_budget=Decimal("200000.00"), is_active=True),
                    ]
                ),
            ]
        )
        # App A spends 25% of its own 400000 allocation; App B spends 45% of its own 200000.
        repo = _make_repo({10: Decimal("100000.00"), 11: Decimal("90000.00")})
        svc = ApplicationUsageService(repo)

        result = await svc.get_application_list("1", auth_db, sort_order="desc")

        # App A spent 100000 (25% of its own 400000), App B spent 90000 (45% of its own
        # 200000) — sorting is by spend AMOUNT, so App A (higher amount) sorts first
        # even though App B has the higher percentage-of-its-own-allocation.
        assert [item.applicationId for item in result.data] == [1, 2]
        app_b = result.data[1]
        assert app_b.allocatedBudget.percentage == 20.0  # % of institution budget
        assert app_b.spendBudget.percentage == 45.0  # % of App B's own allocation
        assert app_b.remainingBudget.percentage == 55.0

    @pytest.mark.asyncio
    async def test_zero_allocation_application_has_no_division_error(self):
        auth_db = _make_auth_db(
            [
                _budget_result(Decimal("1000000.00")),
                _rows_result(
                    [
                        _Row(id=3, name="Sandbox Analytics", domain=None, allocated_percentage=Decimal("0.00"), allocated_budget=Decimal("0.00"), status="ACTIVE"),
                    ]
                ),
                _rows_result([]),
            ]
        )
        repo = _make_repo({})
        svc = ApplicationUsageService(repo)

        result = await svc.get_application_list("1", auth_db)

        item = result.data[0]
        assert item.allocatedBudget.amount == 0.0
        assert item.spendBudget.percentage == 0.0
        assert item.remainingBudget.percentage == 0.0

    @pytest.mark.asyncio
    async def test_pagination_limit_and_offset(self):
        apps = [
            _Row(id=i, name=f"App {i}", domain=None, allocated_percentage=Decimal("10.00"), allocated_budget=Decimal("10000.00"), status="ACTIVE")
            for i in range(1, 4)
        ]
        auth_db = _make_auth_db(
            [_budget_result(Decimal("1000000.00")), _rows_result(apps), _rows_result([])]
        )
        repo = _make_repo({})
        svc = ApplicationUsageService(repo)

        result = await svc.get_application_list("1", auth_db, limit=1, offset=1)

        assert result.total == 3
        assert len(result.data) == 1


class TestGetApplicationDetail:
    @pytest.mark.asyncio
    async def test_application_not_found_raises(self):
        # get_application_detail loads the tenant budget before the applications
        # list, so the mock must supply that result first even for the not-found path.
        auth_db = _make_auth_db([_budget_result(Decimal("1000000.00")), _rows_result([])])
        repo = _make_repo({})
        svc = ApplicationUsageService(repo)

        with pytest.raises(EntityNotFoundError):
            await svc.get_application_detail(999, "1", auth_db)

    @pytest.mark.asyncio
    async def test_detail_includes_masked_keys_and_totals(self):
        # Institution budget = 1,000,000; Citizen Services holds 40% of it (400,000).
        #
        # Key allocated_percentage is a share of the PARENT APPLICATION's budget, not
        # the institution's (api_key_service.py:547: allocated_budget =
        # application.allocated_budget * allocated_percentage / 100, capped at 100%
        # per application by sum_api_key_allocated_percentage). So a key holding
        # 240,000 of Citizen Services' 400,000 is stored as 60.00 (240000/400000),
        # NOT 24.00 (240000/1000000) — this fixture derives allocated_percentage from
        # the real write-path formula so it's a row create_api_key could actually
        # produce, not one that only happens to match the expected institution-scale
        # output by coincidence.
        auth_db = _make_auth_db(
            [
                _budget_result(Decimal("1000000.00")),
                _rows_result(
                    [
                        _Row(id=1, name="Citizen Services", domain="cs.gov", allocated_percentage=Decimal("40.00"), allocated_budget=Decimal("400000.00"), status="ACTIVE"),
                    ]
                ),
                _rows_result(
                    [
                        _Row(id=10, application_id=1, key_name="Web Frontend", api_key="0" * 28 + "a91d", allocated_percentage=Decimal("60.00"), allocated_budget=Decimal("240000.00"), is_active=True),
                        _Row(id=11, application_id=1, key_name="Batch Processing", api_key="0" * 28 + "44f2", allocated_percentage=Decimal("40.00"), allocated_budget=Decimal("160000.00"), is_active=True),
                    ]
                ),
            ]
        )
        repo = _make_repo({10: Decimal("70000.00"), 11: Decimal("30000.00")})
        svc = ApplicationUsageService(repo)

        result = await svc.get_application_detail(1, "1", auth_db)

        assert result.applicationName == "Citizen Services"
        assert result.spendBudget.amount == 100000.0
        assert result.totals.allocatedBudget == 400000.0
        assert result.totals.spendBudget == 100000.0
        assert result.totals.remainingBudget == 300000.0
        keys_by_id = {k.keyId: k for k in result.apiKeys}
        assert keys_by_id[10].maskedKey == "a91d"
        assert keys_by_id[10].spendBudget.percentage == pytest.approx(29.1666, rel=1e-3)
        # allocatedBudget.percentage must be recomputed on the institution scale
        # (240000/1000000=24, 160000/1000000=16) — NOT the raw stored
        # api_key.allocated_percentage (60/40, the app scale), which would make a
        # key appear to hold more of the budget than its own parent application
        # (40%). This is the exact scale-mixing bug: the row's stored percentage
        # (60/40) must differ from the response's percentage (24/16).
        assert keys_by_id[10].allocatedBudget.percentage == 24.0
        assert keys_by_id[11].allocatedBudget.percentage == 16.0
