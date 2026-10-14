"""Live-DB tests for the Usage Dashboard's period queries:
UsageRepository.get_period_usage and
ApplicationUsageRepository.get_period_spend_by_api_key_ids.

Run against a real Postgres migrated to head (usage_events / daily_usage
exist), inside a transaction that is always rolled back — the same approach
as test_migration_usage_and_llm_prices.py. Connection settings come from the
environment, falling back to the alembic .env (CORE_SERVICE_DB_*, then
POSTGRES_*); the tests skip when no database is reachable.
"""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.repositories.pay_per_use.application_usage_repository import ApplicationUsageRepository
from app.repositories.pay_per_use.usage_repository import UsageRepository
from app.utils.usage_period import resolve_period

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

_ALEMBIC_ENV = (
    Path(__file__).resolve().parents[3]
    / "infrastructure" / "databases" / "migrations" / "postgres" / "alembic" / ".env"
)
_TENANT, _OTHER_TENANT = 990001, 990002
_KEY, _OTHER_KEY = 990101, 990102


def _setting(env: dict, name: str):
    for key in (f"CORE_SERVICE_DB_{name}", f"POSTGRES_{name}"):
        value = os.environ.get(key) or env.get(key)
        if value:
            return value
    return None


def _url() -> str:
    env = dotenv_values(_ALEMBIC_ENV) if dotenv_values is not None and _ALEMBIC_ENV.exists() else {}
    parts = {n: _setting(env, n) for n in ("USER", "PASSWORD", "HOST", "PORT")}
    if not all(parts.values()):
        pytest.skip("no ai4iplatform_core DB settings (CORE_SERVICE_DB_* / POSTGRES_*)")
    database = os.environ.get("CORE_SERVICE_DB_NAME") or env.get("CORE_SERVICE_DB_NAME") or "ai4iplatform_core"
    return (
        f"postgresql+asyncpg://{parts['USER']}:{parts['PASSWORD']}"
        f"@{parts['HOST']}:{parts['PORT']}/{database}"
    )


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine(_url(), connect_args={"timeout": 5})
    try:
        conn = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"could not connect to ai4iplatform_core: {exc}")
    trans = await conn.begin()
    try:
        if await conn.scalar(text("SELECT to_regclass('usage_events')")) is None:
            pytest.skip("usage_events doesn't exist; migrate the DB to head first")
        has_span_id = await conn.scalar(text(
            "SELECT 1 FROM information_schema.columns"
            " WHERE table_name = 'usage_events' AND column_name = 'span_id'"
        ))
        if has_span_id:
            pytest.skip("usage_events still has span_id: run `upgrade head` on ai4iplatform_core")
        yield AsyncSession(bind=conn)
    finally:
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture()
def rollup_on(monkeypatch):
    """USAGE_DAILY_ROLLUP_ENABLED: past periods read daily_usage."""
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", True)


@pytest.fixture()
def rollup_off(monkeypatch):
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", False)


async def _type_id(session, name: str) -> int:
    return await session.scalar(text("SELECT id FROM inference_types WHERE name = :n"), {"n": name})


async def _event(session, *, span: str, occurred_at, tenant=_TENANT, key=_KEY, type_id=None,
                 units=0, cached=0, output=0, costs=(0, 0, 0)) -> None:
    await session.execute(text(
        "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, api_key_id,"
        " inference_type_id, task_type, total_units, cached_input_units, output_units,"
        " input_units_cost, cached_input_units_cost, output_units_cost)"
        " VALUES (:correlation_id, :at, :tenant, :key, :type_id, 'llm', :units, :cached, :output,"
        " :c1, :c2, :c3)"
    ), {"correlation_id": f"test-period-{span}", "at": occurred_at, "tenant": tenant, "key": key, "type_id": type_id,
        "units": units, "cached": cached, "output": output,
        "c1": costs[0], "c2": costs[1], "c3": costs[2]})


async def _daily(session, *, usage_date, tenant=_TENANT, key=_KEY, type_id=None, units=0, cost=0) -> None:
    await session.execute(text(
        "INSERT INTO daily_usage (usage_date, billing_month, tenant_id, api_key_id, inference_type_id,"
        " task_type, total_units, input_units_cost)"
        " VALUES (:d, :m, :tenant, :key, :type_id, 'nmt', :units, :cost)"
    ), {"d": usage_date, "m": usage_date.strftime("%Y-%m"), "tenant": tenant, "key": key,
        "type_id": type_id, "units": units, "cost": cost})


@pytest.mark.asyncio
class TestGetPeriodUsage:
    async def test_today_sums_usage_events_in_range_per_tenant_tier_and_type(self, session):
        today = resolve_period("today", None, None)
        llm = await _type_id(session, "llm")
        inside = today.start + timedelta(seconds=1)
        await _event(session, span="s1", occurred_at=inside, type_id=llm, units=1200, cached=1024,
                     output=150, costs=(Decimal("0.0176"), Decimal("0.04096"), Decimal("0.0375")))
        await _event(session, span="s2", occurred_at=inside, type_id=llm, units=100, costs=(Decimal("0.01"), 0, 0))
        await _event(session, span="s3", occurred_at=today.start - timedelta(seconds=1), type_id=llm, units=999)
        await _event(session, span="s4", occurred_at=inside, tenant=_OTHER_TENANT, type_id=llm, units=5)

        rows = await UsageRepository(session).get_period_usage(today, tenant_ids=[str(_TENANT)])

        (row,) = rows
        assert (row.tenant_id, row.inference_type_id, row.task_type, row.task_type_unit) == (
            _TENANT, llm, "llm", "tokens",
        )
        assert (row.total_units, row.cached_input_units, row.output_units) == (1300, 1024, 150)
        assert row.cost == Decimal("0.106060")
        assert row.first_seen == row.last_seen == inside

    async def test_all_tenants_when_none_given(self, session):
        today = resolve_period("today", None, None)
        inside = today.start + timedelta(seconds=1)
        await _event(session, span="a", occurred_at=inside)
        await _event(session, span="b", occurred_at=inside, tenant=_OTHER_TENANT)
        rows = await UsageRepository(session).get_period_usage(today)
        assert {_TENANT, _OTHER_TENANT} <= {r.tenant_id for r in rows}

    async def test_past_periods_read_daily_usage_once_the_rollup_is_on(self, session, rollup_on):
        yesterday = resolve_period("yesterday", None, None)
        nmt = await _type_id(session, "nmt")
        await _daily(session, usage_date=yesterday.from_date, type_id=nmt, units=1900, cost=Decimal("0.08"))
        await _daily(session, usage_date=yesterday.from_date - timedelta(days=1), type_id=nmt, units=50)
        # Today's events never count toward a past period.
        await _event(session, span="t", occurred_at=resolve_period("today", None, None).start + timedelta(seconds=1),
                     type_id=nmt, units=7)

        (row,) = await UsageRepository(session).get_period_usage(yesterday, tenant_ids=[str(_TENANT)])
        assert (row.task_type, row.total_units, row.cost) == ("nmt", 1900, Decimal("0.080000"))
        # A day's IST midnight: daily_usage days come back as instants, like usage_events'.
        assert row.first_seen == row.last_seen == yesterday.start

    async def test_past_periods_read_usage_events_until_the_rollup_is_on(self, session, rollup_off):
        """Without the rollup daily_usage stays empty, so reading it would turn
        every past period into "no institutions"."""
        yesterday = resolve_period("yesterday", None, None)
        nmt = await _type_id(session, "nmt")
        await _event(session, span="y", occurred_at=yesterday.start + timedelta(seconds=1), type_id=nmt, units=40)
        await _event(session, span="e", occurred_at=yesterday.end, type_id=nmt, units=7)  # today 00:00 IST
        await _daily(session, usage_date=yesterday.from_date, type_id=nmt, units=1900)

        (row,) = await UsageRepository(session).get_period_usage(yesterday, tenant_ids=[str(_TENANT)])
        assert (row.task_type, row.total_units) == ("nmt", 40)

    async def test_task_type_filter(self, session):
        today = resolve_period("today", None, None)
        llm, nmt = await _type_id(session, "llm"), await _type_id(session, "nmt")
        inside = today.start + timedelta(seconds=1)
        await _event(session, span="l", occurred_at=inside, type_id=llm, units=10)
        await _event(session, span="n", occurred_at=inside, type_id=nmt, units=20)
        rows = await UsageRepository(session).get_period_usage(
            today, tenant_ids=[str(_TENANT)], task_type_ids=[nmt],
        )
        assert [r.inference_type_id for r in rows] == [nmt]

    async def test_request_rows_are_left_out(self, session):
        """Request rows (a status, no units or cost — one per request, for the
        metering tabs) never show in the Budget tab: an institution whose only
        requests failed isn't listed, and billed figures are unchanged."""
        today = resolve_period("today", None, None)
        inside = today.start + timedelta(seconds=1)
        await session.execute(text(
            "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, status_code, total_units)"
            " VALUES ('test-period-req-1', :at, :t, 502, 0), ('test-period-req-2', :at2, :t2, 200, 0)"
        ), {"at": inside, "t": _OTHER_TENANT, "at2": inside + timedelta(seconds=1), "t2": _TENANT})
        await _event(session, span="billed", occurred_at=inside, units=10, costs=(Decimal("1"), 0, 0))

        rows = await UsageRepository(session).get_period_usage(today, tenant_ids=[str(_TENANT), str(_OTHER_TENANT)])
        assert {r.tenant_id for r in rows} == {_TENANT}
        assert sum(r.total_units for r in rows) == 10

    async def test_non_numeric_tenant_ids_match_nothing(self, session):
        today = resolve_period("today", None, None)
        assert await UsageRepository(session).get_period_usage(today, tenant_ids=["abc"]) == []


@pytest.mark.asyncio
class TestGetPeriodSpendByApiKeyIds:
    async def test_today_from_usage_events(self, session):
        today = resolve_period("today", None, None)
        inside = today.start + timedelta(seconds=1)
        await _event(session, span="k1", occurred_at=inside, costs=(Decimal("1.5"), 0, Decimal("0.5")))
        await _event(session, span="k2", occurred_at=inside, costs=(Decimal("1"), 0, 0))
        await _event(session, span="k3", occurred_at=inside, key=_OTHER_KEY, costs=(Decimal("9"), 0, 0))

        spend = await ApplicationUsageRepository(session).get_period_spend_by_api_key_ids(today, [_KEY])
        assert spend == {_KEY: Decimal("3.000000")}

    async def test_past_period_from_daily_usage(self, session, rollup_on):
        last_7 = resolve_period("last_7_days", None, None)
        await _daily(session, usage_date=last_7.from_date, cost=Decimal("2"))
        await _daily(session, usage_date=last_7.to_date, cost=Decimal("3"))
        await _daily(session, usage_date=last_7.from_date - timedelta(days=1), cost=Decimal("100"))

        spend = await ApplicationUsageRepository(session).get_period_spend_by_api_key_ids(last_7, [_KEY, _OTHER_KEY])
        assert spend == {_KEY: Decimal("5.000000")}

    async def test_past_period_from_usage_events_without_the_rollup(self, session, rollup_off):
        last_7 = resolve_period("last_7_days", None, None)
        await _event(session, span="p", occurred_at=last_7.end - timedelta(seconds=1), costs=(Decimal("4"), 0, 0))
        spend = await ApplicationUsageRepository(session).get_period_spend_by_api_key_ids(last_7, [_KEY])
        assert spend == {_KEY: Decimal("4.000000")}

    async def test_no_keys_is_empty_without_a_query(self, session):
        today = resolve_period("today", None, None)
        assert await ApplicationUsageRepository(session).get_period_spend_by_api_key_ids(today, []) == {}


@pytest.mark.asyncio
class TestUsageDataFrom:
    async def test_rows_before_the_period_mean_it_is_fully_covered(self, session, rollup_off):
        yesterday = resolve_period("yesterday", None, None)
        await _event(session, span="old", occurred_at=yesterday.start - timedelta(hours=1))
        assert await UsageRepository(session).get_usage_data_from(yesterday) == yesterday.start

    async def test_recording_began_inside_the_period(self, session, rollup_off):
        """Holds only while the test DB has no rows from before today; the
        transaction is rolled back, so the shared DB keeps none."""
        today = resolve_period("today", None, None)
        if await session.scalar(text("SELECT 1 FROM usage_events WHERE occurred_at < :s LIMIT 1"),
                                {"s": today.start}):
            pytest.skip("usage_events already holds rows from before today")
        first = today.start + timedelta(seconds=5)
        await _event(session, span="first", occurred_at=first)
        await _event(session, span="later", occurred_at=first + timedelta(seconds=1))
        assert await ApplicationUsageRepository(session).get_usage_data_from(today) == first

    async def test_no_data_for_the_period(self, session, rollup_off):
        today = resolve_period("today", None, None)
        if await session.scalar(text("SELECT 1 FROM usage_events WHERE occurred_at < :e LIMIT 1"),
                                {"e": today.end}):
            pytest.skip("usage_events already holds rows")
        assert await UsageRepository(session).get_usage_data_from(today) is None

    async def test_daily_usage_with_the_rollup_on(self, session, rollup_on):
        last_7 = resolve_period("last_7_days", None, None)
        if await session.scalar(text("SELECT 1 FROM daily_usage WHERE usage_date <= :d LIMIT 1"),
                                {"d": last_7.to_date}):
            pytest.skip("daily_usage already holds rows up to the period's end")
        await _daily(session, usage_date=last_7.to_date, units=10, cost=Decimal("1"))
        # The IST midnight that starts the day.
        assert await UsageRepository(session).get_usage_data_from(last_7) == last_7.end - timedelta(days=1)
