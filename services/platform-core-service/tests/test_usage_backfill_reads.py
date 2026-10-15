"""Live-DB tests for how the Usage Dashboard reads the Prometheus backfill
(pyjob usage_backfill): daily_usage rows with source 'backfill', estimates,
covering the span usage_backfill records, up to where usage_events takes over.

Run against a real Postgres migrated to head, inside a transaction that is
always rolled back — same approach and connection settings as
test_period_usage_repository.py; skipped when no database is reachable.

The backfill covers 2025-01-10 and 2025-01-11 and, on 2025-01-12, up to
11:30 IST, where usage_events begins.
"""
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.repositories.pay_per_use.application_usage_repository import ApplicationUsageRepository
from app.repositories.pay_per_use.metering_usage import MeteringUsageRepository
from app.repositories.pay_per_use.usage_repository import UsageRepository
from app.services.metering_service_usage_events import UsageEventsMeteringService
from app.utils.usage_period import IST, resolve_period

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

_ALEMBIC_ENV = (
    Path(__file__).resolve().parents[3]
    / "infrastructure" / "databases" / "migrations" / "postgres" / "alembic" / ".env"
)
_TENANT = 990401
_SINGLE_APP, _MULTI_APP = 990411, 990412
_KEY = 990421
_FIRST, _BOUNDARY = date(2025, 1, 10), date(2025, 1, 12)
_UNTIL = datetime(2025, 1, 12, 11, 30, tzinfo=IST)


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
        if await conn.scalar(text("SELECT to_regclass('usage_backfill')")) is None:
            pytest.skip("usage_backfill doesn't exist; migrate the DB to head first")
        yield AsyncSession(bind=conn)
    finally:
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture()
def rollup_on(monkeypatch):
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", True)


@pytest.fixture()
def rollup_off(monkeypatch):
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", False)


def _mid(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=IST).astimezone(timezone.utc)


def _period(first: date, last: date):
    return resolve_period("custom", first.isoformat(), last.isoformat())


async def _daily(session, day: date, *, source="backfill", app=_SINGLE_APP, key=_KEY,
                 requests=0, failed=0, units=0, output=0, cost=Decimal(0)) -> None:
    await session.execute(text(
        "INSERT INTO daily_usage (usage_date, billing_month, tenant_id, application_id, api_key_id,"
        " inference_type_id, task_type, source, request_count, success_count, failed_count,"
        " total_units, output_units, input_units_cost)"
        " VALUES (:d, :m, :t, :app, :key, (SELECT id FROM inference_types WHERE name = 'llm'), 'llm',"
        " :source, :r, :ok, :f, :u, :o, :c)"
    ), {"d": day, "m": day.strftime("%Y-%m"), "t": _TENANT, "app": app, "key": key, "source": source,
        "r": requests, "ok": requests - failed, "f": failed, "u": units, "o": output, "c": cost})


async def _event(session, corr: str, at: datetime, *, status=None, units=0, cost=Decimal(0)) -> None:
    await session.execute(text(
        "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, application_id, api_key_id,"
        " inference_type_id, task_type, status_code, total_units, input_units_cost)"
        " VALUES (:c, :at, :t, :app, :key, (SELECT id FROM inference_types WHERE name = 'llm'), 'llm',"
        " :st, :u, :cost)"
    ), {"c": corr, "at": at, "t": _TENANT, "app": _SINGLE_APP, "key": _KEY, "st": status, "u": units,
        "cost": cost})


async def _seed(session) -> None:
    """Backfilled 10, 11 and the morning of 12 Jan 2025; recorded from 11:30
    IST on the 12th (a request row and its usage row)."""
    await session.execute(text(
        "INSERT INTO usage_backfill (id, first_day, until) VALUES (1, :f, :u)"
        " ON CONFLICT (id) DO UPDATE SET first_day = EXCLUDED.first_day, until = EXCLUDED.until"
    ), {"f": _FIRST, "u": _UNTIL})
    await _daily(session, _FIRST, requests=10, failed=1, units=1000, output=200, cost=Decimal("2"))
    await _daily(session, _FIRST + timedelta(days=1), requests=5, units=500, output=100, cost=Decimal("1"))
    await _daily(session, _FIRST + timedelta(days=1), app=_MULTI_APP, key=None, requests=4, units=400,
                 cost=Decimal("3"))
    await _daily(session, _BOUNDARY, requests=2, units=200, output=50, cost=Decimal("0.5"))
    at = _UNTIL.astimezone(timezone.utc) + timedelta(hours=1)
    await _event(session, "bf-req", at, status=200)
    await _event(session, "bf-req", at + timedelta(seconds=1), units=300, cost=Decimal("0.7"))


@pytest.mark.asyncio
class TestMeteringReads:
    async def test_backfill_days_count_with_the_rollup_off(self, session, rollup_off):
        await _seed(session)
        repo = MeteringUsageRepository(session)
        rows = await repo.aggregate(_mid(_FIRST), _mid(_BOUNDARY + timedelta(days=1)), tenant_id=_TENANT)
        agg = rows[()]
        # 10 + 5 + 4 + 2 backfilled, 1 recorded after 11:30 on the 12th.
        assert (agg.requests, agg.failed, agg.units, agg.output_units) == (22, 1, 2400, 350)

    async def test_the_boundary_day_adds_its_rollup_rows(self, session, rollup_on):
        """With the rollup on, the 12th has a rollup row (from 11:30) and a
        backfill row (before it): both count, nothing twice."""
        await _seed(session)
        await _daily(session, _BOUNDARY, source="rollup", requests=1, units=300, cost=Decimal("0.7"))
        repo = MeteringUsageRepository(session)
        rows = await repo.aggregate(_mid(_BOUNDARY), _mid(_BOUNDARY + timedelta(days=1)), tenant_id=_TENANT)
        assert (rows[()].requests, rows[()].units) == (3, 500)

    async def test_a_day_inside_the_backfill_reads_only_its_estimates(self, session, rollup_off):
        await _seed(session)
        repo = MeteringUsageRepository(session)
        day = _FIRST + timedelta(days=1)
        rows = await repo.aggregate(_mid(day), _mid(day + timedelta(days=1)), ("service_id",), tenant_id=_TENANT)
        assert {k: (a.requests, a.units) for k, a in rows.items()} == {(None,): (9, 900)}

    async def test_coverage_and_recorded_from(self, session, rollup_off):
        await _seed(session)
        svc = UsageEventsMeteringService(session)
        assert await svc.recorded_from() == _UNTIL
        # From the day before the backfill: data from its first day.
        period = _period(_FIRST - timedelta(days=1), _BOUNDARY)
        block = period.to_schema(await svc.data_since(period), await svc.recorded_from())
        assert (block.dataFrom, block.partial) == ("2025-01-10T00:00:00+05:30", True)
        assert block.recordedFrom == "2025-01-12T11:30:00+05:30"
        # Long before the backfill: no data.
        old = _period(date(2001, 1, 1), date(2001, 1, 2))
        assert await svc.data_since(old) is None

    async def test_previous_window_inside_the_backfill_is_covered(self, session, rollup_off):
        await _seed(session)
        svc = UsageEventsMeteringService(session)
        assert await svc._covered(_mid(_FIRST), _mid(_FIRST + timedelta(days=1)))
        assert not await svc._covered(_mid(_FIRST - timedelta(days=1)), _mid(_FIRST))

    async def test_first_usage_is_the_first_backfilled_day(self, session, rollup_off):
        await _seed(session)
        repo = MeteringUsageRepository(session)
        assert await repo.first_usage(_TENANT) == _mid(_FIRST)


@pytest.mark.asyncio
class TestBudgetAndApplicationReads:
    async def test_period_usage_adds_the_estimates(self, session, rollup_off):
        await _seed(session)
        repo = UsageRepository(session)
        period = _period(_FIRST, _BOUNDARY)
        rows = await repo.get_period_usage(period, tenant_ids=[str(_TENANT)])
        assert sum(r.cost for r in rows) == Decimal("7.2")      # 2 + 1 + 3 + 0.5 backfilled, 0.7 recorded
        assert all(isinstance(r.first_seen, datetime) for r in rows)
        recorded = await repo.get_period_usage(period, tenant_ids=[str(_TENANT)], include_backfill=False)
        assert sum(r.cost for r in recorded) == Decimal("0.7")

    async def test_period_coverage(self, session, rollup_off):
        await _seed(session)
        repo = UsageRepository(session)
        period = _period(_FIRST - timedelta(days=1), _BOUNDARY)
        assert await repo.get_usage_data_from(period) == _mid(_FIRST)
        assert await repo.get_recorded_from() == _UNTIL

    async def test_key_spend_is_recorded_only_and_estimates_are_per_application(self, session, rollup_off):
        await _seed(session)
        repo = ApplicationUsageRepository(session)
        period = _period(_FIRST, _BOUNDARY)
        # The key's recorded 0.7 only, though the single-key app's backfill rows carry it.
        assert await repo.get_period_spend_by_api_key_ids(period, [_KEY]) == {_KEY: Decimal("0.7")}
        assert await repo.get_backfill_period_spend(period, [_SINGLE_APP, _MULTI_APP]) == {
            _SINGLE_APP: Decimal("3.5"), _MULTI_APP: Decimal("3"),
        }
        later = _period(_BOUNDARY + timedelta(days=1), _BOUNDARY + timedelta(days=1))
        assert await repo.get_backfill_period_spend(later, [_MULTI_APP]) == {}
