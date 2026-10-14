"""daily_usage_consolidation's _AGGREGATE: how requests are counted.

Request rows (status set, no units) count one each — calls that reuse one
X-Correlation-ID are separate requests. Usage rows from before request rows
existed (status set, with units) count once per correlation id. Rows without
a status add units and cost only.

Live-DB: runs the job's own _AGGREGATE against a Postgres migrated to head,
inside a transaction that is always rolled back. Connection settings come
from CORE_SERVICE_DB_* (then POSTGRES_*); skipped when no database is
reachable.
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jobs.daily_usage_consolidation import _AGGREGATE  # noqa: E402

_DAY = date(2026, 10, 13)
_START = datetime.combine(_DAY, time(), tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
_TENANT = 990301
_TIER_A, _TIER_B = "5ab0c0de-0000-4000-8000-00000000000a", "5ab0c0de-0000-4000-8000-00000000000b"


def _url() -> str:
    def setting(name):
        return os.environ.get(f"CORE_SERVICE_DB_{name}") or os.environ.get(f"POSTGRES_{name}")

    parts = {n: setting(n) for n in ("USER", "PASSWORD", "HOST", "PORT")}
    if not all(parts.values()):
        pytest.skip("no ai4iplatform_core DB settings (CORE_SERVICE_DB_* / POSTGRES_*)")
    database = os.environ.get("CORE_SERVICE_DB_NAME") or "ai4iplatform_core"
    return f"postgresql://{parts['USER']}:{parts['PASSWORD']}@{parts['HOST']}:{parts['PORT']}/{database}"


@pytest.fixture()
def conn():
    engine = create_engine(_url(), connect_args={"connect_timeout": 5})
    try:
        connection = engine.connect()
    except Exception as exc:
        pytest.skip(f"could not connect to ai4iplatform_core: {exc}")
    trans = connection.begin()
    try:
        if connection.scalar(text("SELECT to_regclass('usage_events')")) is None:
            pytest.skip("usage_events doesn't exist; migrate the DB to head first")
        connection.execute(text("INSERT INTO tiers (id, name) VALUES (:a, 'rollup-test-a'), (:b, 'rollup-test-b')"),
                           {"a": _TIER_A, "b": _TIER_B})
        yield connection
    finally:
        trans.rollback()
        connection.close()
        engine.dispose()


def _row(conn, correlation_id, seconds, *, status=None, units=0, tier=_TIER_A):
    conn.execute(text(
        "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, tier_id, status_code, total_units)"
        " VALUES (:c, :at, :t, :tier, :status, :units)"
    ), {"c": correlation_id, "at": _START + timedelta(hours=10, seconds=seconds), "t": _TENANT,
        "tier": tier, "status": status, "units": units})


def _groups(conn) -> dict:
    """{tier_id: (request_count, failed_count, success_count, total_units)} for the test tenant."""
    rows = conn.execute(_AGGREGATE, {"start": _START, "end": _START + timedelta(days=1)}).mappings().all()
    return {
        str(r["tier_id"]): (r["request_count"], r["failed_count"], r["success_count"], r["total_units"])
        for r in rows if r["tenant_id"] == _TENANT
    }


def test_reused_correlation_id_counts_every_request(conn):
    _row(conn, "rollup-reused", 0, status=200)
    _row(conn, "rollup-reused", 30, status=502)
    assert _groups(conn) == {_TIER_A: (2, 1, 1, 0)}


def test_request_row_and_its_usage_row_are_one_request(conn):
    _row(conn, "rollup-req", 1, status=200)
    _row(conn, "rollup-req", 0, units=100)       # the usage row: no status
    assert _groups(conn) == {_TIER_A: (1, 0, 1, 100)}


def test_pre_cutover_rows_count_once_per_correlation_id(conn):
    _row(conn, "rollup-old", 0, status=200, units=40)
    _row(conn, "rollup-old", 2, status=200, units=60)
    assert _groups(conn) == {_TIER_A: (1, 0, 1, 100)}


def test_request_counts_in_its_own_group_only(conn):
    _row(conn, "rollup-split", 1, status=200, tier=_TIER_A)
    _row(conn, "rollup-split", 0, units=100, tier=_TIER_B)
    assert _groups(conn) == {_TIER_A: (1, 0, 1, 0), _TIER_B: (0, 0, 0, 100)}
