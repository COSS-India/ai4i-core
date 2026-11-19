"""daily_usage_consolidation's _AGGREGATE: how requests are counted.

Request rows (status set, no units) count one each — calls that reuse one
X-Correlation-ID are separate requests. Usage rows from before request rows
existed (status set, with units) count once per correlation id. Rows without
a status add units and cost only.

Live-DB: runs the job's own _AGGREGATE against a Postgres migrated to head,
inside a transaction that is always rolled back, through asyncpg as the job
does. Connection settings are pyjob's own: PLATFORM_CORE_DB_* (then
POSTGRES_*, see bootstrap.config); skipped when no database is reachable.
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jobs.daily_usage_consolidation import _AGGREGATE, _DELETE_STALE  # noqa: E402

_DAY = date(2026, 10, 13)
_START = datetime.combine(_DAY, time(), tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
_TENANT = 990301
_TIER_A, _TIER_B = "5ab0c0de-0000-4000-8000-00000000000a", "5ab0c0de-0000-4000-8000-00000000000b"


def _url() -> str:
    """pyjob's own settings (bootstrap.config): PLATFORM_CORE_DB_*, falling
    back to POSTGRES_*."""
    def setting(name):
        return os.environ.get(f"PLATFORM_CORE_DB_{name}") or os.environ.get(f"POSTGRES_{name}")

    parts = {n: setting(n) for n in ("USER", "PASSWORD", "HOST", "PORT")}
    if not all(parts.values()):
        pytest.skip("no ai4iplatform_core DB settings (PLATFORM_CORE_DB_* / POSTGRES_*)")
    database = os.environ.get("PLATFORM_CORE_DB_NAME") or "ai4iplatform_core"
    return f"postgresql+asyncpg://{parts['USER']}:{parts['PASSWORD']}@{parts['HOST']}:{parts['PORT']}/{database}"


@pytest_asyncio.fixture()
async def conn():
    engine = create_async_engine(_url(), connect_args={"timeout": 5})
    try:
        connection = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"could not connect to ai4iplatform_core: {exc}")
    trans = await connection.begin()
    try:
        if await connection.scalar(text("SELECT to_regclass('usage_events')")) is None:
            pytest.skip("usage_events doesn't exist; migrate the DB to head first")
        await connection.execute(
            text("INSERT INTO tiers (id, name, status) VALUES"
                 " (:a, 'rollup-test-a', 'ACTIVE'), (:b, 'rollup-test-b', 'ACTIVE')"),
            {"a": _TIER_A, "b": _TIER_B},
        )
        yield connection
    finally:
        await trans.rollback()
        await connection.close()
        await engine.dispose()


async def _row(conn, correlation_id, seconds, *, status=None, units=0, tier=_TIER_A,
               fallback=False, response_ms=None):
    await conn.execute(text(
        "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, tier_id, status_code, total_units,"
        " sent_to_fallback, response_time_ms)"
        " VALUES (:c, :at, :t, :tier, :status, :units, :fallback, :ms)"
    ), {"c": correlation_id, "at": _START + timedelta(hours=10, seconds=seconds), "t": _TENANT,
        "tier": tier, "status": status, "units": units, "fallback": fallback, "ms": response_ms})


async def _groups(conn) -> dict:
    """{tier_id: (request_count, failed_count, success_count, total_units)} for the test tenant."""
    rows = (await conn.execute(_AGGREGATE, {"start": _START, "end": _START + timedelta(days=1)})).mappings().all()
    return {
        str(r["tier_id"]): (r["request_count"], r["failed_count"], r["success_count"], r["total_units"])
        for r in rows if r["tenant_id"] == _TENANT
    }


@pytest.mark.asyncio
async def test_reused_correlation_id_counts_every_request(conn):
    await _row(conn, "rollup-reused", 0, status=200)
    await _row(conn, "rollup-reused", 30, status=502)
    assert await _groups(conn) == {_TIER_A: (2, 1, 1, 0)}


@pytest.mark.asyncio
async def test_request_row_and_its_usage_row_are_one_request(conn):
    await _row(conn, "rollup-req", 1, status=200)
    await _row(conn, "rollup-req", 0, units=100)       # the usage row: no status
    assert await _groups(conn) == {_TIER_A: (1, 0, 1, 100)}


@pytest.mark.asyncio
async def test_pre_cutover_rows_count_once_per_correlation_id(conn):
    await _row(conn, "rollup-old", 0, status=200, units=40)
    await _row(conn, "rollup-old", 2, status=200, units=60)
    assert await _groups(conn) == {_TIER_A: (1, 0, 1, 100)}


@pytest.mark.asyncio
async def test_request_counts_in_its_own_group_only(conn):
    await _row(conn, "rollup-split", 1, status=200, tier=_TIER_A)
    await _row(conn, "rollup-split", 0, units=100, tier=_TIER_B)
    assert await _groups(conn) == {_TIER_A: (1, 0, 1, 0), _TIER_B: (0, 0, 0, 100)}


async def _health(conn) -> dict:
    """{tier_id: (server_error_count, fallback_count, total_response_time_ms, response_time_count)}
    for the test tenant. fallback_count is the aggregate's integer part; the
    upsert builds the JSON from it and fallback_success / fallback_failure."""
    rows = (await conn.execute(_AGGREGATE, {"start": _START, "end": _START + timedelta(days=1)})).mappings().all()
    return {
        str(r["tier_id"]): (
            r["server_error_count"], r["fallback_count"], r["total_response_time_ms"], r["response_time_count"],
        )
        for r in rows if r["tenant_id"] == _TENANT
    }


@pytest.mark.asyncio
async def test_server_errors_fallbacks_and_response_time_from_request_rows(conn):
    await _row(conn, "rollup-h1", 0, status=200, fallback=True, response_ms=120)
    await _row(conn, "rollup-h2", 1, status=502, response_ms=4000)
    await _row(conn, "rollup-h3", 2, status=429, response_ms=15)    # the client's error, not the platform's
    await _row(conn, "rollup-h4", 3, status=200)                    # no response time recorded
    await _row(conn, "rollup-h1", -1, units=100)                    # h1's usage row: adds nothing here
    assert await _groups(conn) == {_TIER_A: (4, 2, 2, 100)}
    assert await _health(conn) == {_TIER_A: (1, 1, 4135, 3)}   # h4 has no time: not in the divisor


async def _fallbacks(conn) -> dict:
    """{tier_id: (fallback_count, fallback_success, fallback_failure)} for the test tenant."""
    rows = (await conn.execute(_AGGREGATE, {"start": _START, "end": _START + timedelta(days=1)})).mappings().all()
    return {
        str(r["tier_id"]): (r["fallback_count"], r["fallback_success"], r["fallback_failure"])
        for r in rows if r["tenant_id"] == _TENANT
    }


@pytest.mark.asyncio
async def test_fallbacks_split_into_success_and_failure_by_status(conn):
    await _row(conn, "rollup-f1", 0, status=200, fallback=True)
    await _row(conn, "rollup-f2", 1, status=503, fallback=True)    # the fallback failed too
    await _row(conn, "rollup-f3", 2, status=429, fallback=True)
    await _row(conn, "rollup-f4", 3, status=500)                   # not sent to a fallback
    assert await _fallbacks(conn) == {_TIER_A: (3, 1, 2)}


@pytest.mark.asyncio
async def test_pre_cutover_server_errors_count_once_per_correlation_id(conn):
    await _row(conn, "rollup-old-5xx", 0, status=503, units=40)
    await _row(conn, "rollup-old-5xx", 2, status=503, units=60)
    assert await _health(conn) == {_TIER_A: (1, 0, 0, 0)}


async def _daily_usage_row(conn, tenant_id, source):
    # updated_at in the past so it is "stale" relative to the rollup's now()
    # (the transaction start); distinct tenant_id so the two rows don't share
    # the (source-less) unique dimension key.
    await conn.execute(text(
        "INSERT INTO daily_usage (usage_date, tenant_id, billing_month, source,"
        " request_count, success_count, failed_count, updated_at)"
        " VALUES (:d, :t, '2026-10', :src, 1, 1, 0, now() - interval '1 hour')"
    ), {"d": _DAY, "t": tenant_id, "src": source})


@pytest.mark.asyncio
async def test_delete_stale_removes_rollup_rows_but_spares_backfill(conn):
    # The source = 'rollup' filter in _DELETE_STALE is the only thing stopping
    # the nightly rollup from deleting backfilled estimates: a stale rollup row
    # is swept, a backfill row on the same day is kept.
    await _daily_usage_row(conn, _TENANT, "rollup")
    await _daily_usage_row(conn, _TENANT + 1, "backfill")
    await conn.execute(_DELETE_STALE, {"usage_date": _DAY})
    rows = (await conn.execute(text(
        "SELECT source::text AS source, count(*) AS n FROM daily_usage"
        " WHERE usage_date = :d AND tenant_id IN (:a, :b) GROUP BY source"
    ), {"d": _DAY, "a": _TENANT, "b": _TENANT + 1})).mappings().all()
    assert {r["source"]: r["n"] for r in rows} == {"backfill": 1}
