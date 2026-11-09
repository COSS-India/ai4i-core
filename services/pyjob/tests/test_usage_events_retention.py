"""daily_usage_consolidation's retention (step 3): usage_events days past
USAGE_EVENTS_RETENTION_DAYS are rolled up a last time and dropped.

Live-DB, and unlike test_rollup_request_counts this one commits: the job
runs as it does in production (its own sessions, partition DDL). Opt in with
PYJOB_RETENTION_TEST=1 and point PLATFORM_CORE_DB_* / AUTH_DB_* (then
POSTGRES_*) at a disposable copy of the databases migrated to head. The
tests run the job for a "today" in January 2001, so only their own days are
past the retention, and remove what they create.
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bootstrap import database  # noqa: E402
from bootstrap.config import get_settings  # noqa: E402
from jobs import daily_usage_consolidation as job  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
TODAY = date(2001, 1, 20)
CUTOFF = TODAY - timedelta(days=3)           # the default retention: 17 Jan is kept, 16 Jan dropped
OLD, KEPT = CUTOFF - timedelta(days=1), CUTOFF
_TENANT = 990401

pytestmark = pytest.mark.skipif(
    os.environ.get("PYJOB_RETENTION_TEST") != "1",
    reason="commits partition DDL: set PYJOB_RETENTION_TEST=1 against a disposable database",
)


def _at(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=IST).astimezone(timezone.utc)


async def _sql(sql: str, params: dict | None = None):
    async with database.platform_core_session() as session:
        async with session.begin():
            result = await session.execute(text(sql), params or {})
            return result.all() if result.returns_rows else []


async def _partition(day: date) -> None:
    await _sql(
        f'CREATE TABLE "{job._day_name(day)}" PARTITION OF usage_events '
        f"FOR VALUES FROM ({job._bound(day)}) TO ({job._bound(day + timedelta(days=1))})"
    )


async def _request(day: date, corr: str, status: int = 200, hour: int = 10) -> None:
    await _sql(
        "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, status_code, total_units,"
        " response_time_ms) VALUES (:c, :at, :t, :s, 0, 100)",
        {"c": corr, "at": _at(day, hour), "t": _TENANT, "s": status},
    )


async def _usage(day: date, corr: str, units: int, cost: str = "1.50", hour: int = 11) -> None:
    await _sql(
        "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, total_units, input_units_cost)"
        " VALUES (:c, :at, :t, :u, :cost)",
        {"c": corr, "at": _at(day, hour), "t": _TENANT, "u": units, "cost": cost},
    )


async def _daily(day: date) -> tuple:
    """(requests, failed, units, cost) of the test tenant's daily_usage rows on ``day``."""
    (row,) = await _sql(
        "SELECT coalesce(sum(request_count), 0), coalesce(sum(failed_count), 0),"
        " coalesce(sum(total_units), 0), coalesce(sum(cost), 0)"
        " FROM daily_usage WHERE usage_date = :d AND tenant_id = :t",
        {"d": day, "t": _TENANT},
    )
    return tuple(int(v) if i < 3 else float(v) for i, v in enumerate(row))


async def _has_partition(day: date) -> bool:
    return (await _sql("SELECT to_regclass(:n) IS NOT NULL", {"n": job._day_name(day)}))[0][0]


async def _raw_rows(day: date) -> int:
    return (await _sql(
        "SELECT count(*) FROM usage_events WHERE occurred_at >= :s AND occurred_at < :e",
        {"s": _at(day, 0), "e": _at(day + timedelta(days=1), 0)},
    ))[0][0]


@pytest_asyncio.fixture(autouse=True)
async def db(monkeypatch):
    get_settings.cache_clear()
    database.init_databases()
    try:
        await _sql("SELECT 1 FROM usage_events LIMIT 1")
    except Exception as exc:
        await database.close_databases()
        pytest.skip(f"no migrated ai4iplatform_core (usage_events): {exc}")
    try:
        yield
    finally:
        start, end = _at(date(2000, 12, 1), 0), _at(date(2001, 2, 1), 0)
        async with database.platform_core_session() as session:
            async with session.begin():
                names = (await session.execute(text(
                    "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid"
                    " WHERE i.inhparent = 'usage_events'::regclass AND c.relname LIKE 'usage_events_2001_%'"
                ))).scalars().all()
                for name in names:
                    await session.execute(text(f'DROP TABLE "{name}"'))
                await session.execute(text(
                    "DELETE FROM usage_events WHERE occurred_at >= :s AND occurred_at < :e"), {"s": start, "e": end})
                await session.execute(text(
                    "DELETE FROM daily_usage WHERE usage_date >= '2000-12-01' AND usage_date < '2001-02-01'"))
        await database.close_databases()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_old_day_is_rolled_up_then_dropped():
    await _partition(OLD)
    await _request(OLD, "ret-1")
    await _usage(OLD, "ret-1", 100)
    await _request(OLD, "ret-2", status=503)

    await job.consolidate(TODAY)

    assert await _daily(OLD) == (2, 1, 100, 1.5)
    assert not await _has_partition(OLD)
    assert await _raw_rows(OLD) == 0


@pytest.mark.asyncio
async def test_days_within_the_retention_are_kept():
    for day in (KEPT, TODAY - timedelta(days=1)):
        await _partition(day)
        await _request(day, f"ret-keep-{day}")

    await job.consolidate(TODAY)

    for day in (KEPT, TODAY - timedelta(days=1)):
        assert await _has_partition(day)
        assert await _raw_rows(day) == 1


@pytest.mark.asyncio
async def test_a_failed_rollup_drops_nothing(monkeypatch):
    await _partition(OLD)
    await _request(OLD, "ret-fail")

    async def failing(day):
        raise RuntimeError("rollup down")

    monkeypatch.setattr(job, "_rollup_day", failing)
    with pytest.raises(RuntimeError, match="rollup"):
        await job.consolidate(TODAY)

    assert await _has_partition(OLD)
    assert await _raw_rows(OLD) == 1


@pytest.mark.asyncio
async def test_a_failure_while_dropping_rolls_the_day_back(monkeypatch):
    """The last rollup and the drop are one transaction: if the drop fails,
    the day keeps its rows and its partition, so the next run rolls it up
    again rather than taking its rows for late ones."""
    await _partition(OLD)
    await _request(OLD, "ret-atomic")
    real = job._summarise

    async def summarise_then_fail(session, day):
        rows = await real(session, day)
        if day == OLD:
            await session.execute(job._UPSERT, rows)
            raise RuntimeError("drop failed")
        return rows

    monkeypatch.setattr(job, "_summarise", summarise_then_fail)
    with pytest.raises(RuntimeError, match=f"retention {OLD}"):
        await job.consolidate(TODAY)

    assert await _has_partition(OLD)
    assert await _raw_rows(OLD) == 1
    assert await _daily(OLD) == (0, 0, 0, 0.0)


@pytest.mark.asyncio
async def test_totals_are_unchanged_by_the_drop():
    """What daily_usage holds for a day the rollup already summarised is the
    same after its usage_events rows are gone — including rows that arrived
    after the lookback last re-read it, which the last rollup picks up."""
    await _partition(OLD)
    await _request(OLD, "ret-same-1")
    await _usage(OLD, "ret-same-1", 40, "0.40")
    await job._rollup_day(OLD)                       # the nightly lookback, days ago
    before = await _daily(OLD)
    await _request(OLD, "ret-same-late", hour=23)    # arrived after that rollup

    await job.consolidate(TODAY)

    assert before == (1, 0, 40, 0.4)
    assert await _daily(OLD) == (2, 0, 40, 0.4)
    assert await _raw_rows(OLD) == 0


@pytest.mark.asyncio
async def test_rows_arriving_for_a_dropped_day_are_added_not_rolled_up_again():
    await _partition(OLD)
    await _request(OLD, "ret-late-1")
    await _usage(OLD, "ret-late-1", 100)
    await job.consolidate(TODAY)
    assert await _daily(OLD) == (1, 0, 100, 1.5)

    # Kafka redelivers a request days late: no partition, so it lands in DEFAULT.
    await _request(OLD, "ret-late-2", status=500, hour=22)
    assert await _raw_rows(OLD) == 1

    await job.consolidate(TODAY + timedelta(days=1))

    assert await _daily(OLD) == (2, 1, 100, 1.5)     # added to what was there
    assert not await _has_partition(OLD)             # the partition step didn't recreate it
    assert await _raw_rows(OLD) == 0


@pytest.mark.asyncio
async def test_late_rows_of_a_dropped_day_get_no_partition_back():
    """A partition would make the late rows look like the whole day, which
    the last rollup would then replace the day's rows with."""
    await _partition(OLD)
    await _request(OLD, "ret-nopart-1")
    await _request(OLD, "ret-nopart-2")
    await job.consolidate(TODAY)
    await _request(OLD, "ret-nopart-late", hour=22)       # lands in DEFAULT

    await job._maintain_partitions(TODAY + timedelta(days=1))

    assert not await _has_partition(OLD)
    assert await _raw_rows(OLD) == 1
    assert await _daily(OLD) == (2, 0, 0, 0.0)


@pytest.mark.asyncio
async def test_a_backfilled_day_is_dropped_without_a_rollup():
    """The dashboard shows a backfilled day's estimates instead of its
    usage_events rows; a rollup would add them on top."""
    await _partition(OLD)
    await _request(OLD, "ret-backfill")
    await _sql(
        "INSERT INTO daily_usage (usage_date, tenant_id, billing_month, source, request_count, success_count)"
        " VALUES (:d, :t, '2001-01', 'backfill', 5, 5)",
        {"d": OLD, "t": _TENANT},
    )

    await job.consolidate(TODAY)

    assert await _daily(OLD) == (5, 0, 0, 0.0)
    assert not await _has_partition(OLD)
    assert await _raw_rows(OLD) == 0

