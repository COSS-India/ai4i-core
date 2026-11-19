"""jobs/key_expiry_alerts.py's candidate queries against Postgres: which
reminder level each key is due today.

The level rules (l >= days_left, l < span_days, calendar days in
NOTIFICATION_TIMEZONE, the grace-after-expiry exclusion) live only in the
SQL, so they are checked here on real tables, not stubs.

Live-DB: runs the job's own _GRACE_PERIOD_KEY_SQL / _EXPIRING_API_KEY_SQL
against an ai4iplatform_auth migrated to head, inside a transaction that is
always rolled back. Connection settings are pyjob's own: AUTH_DB_* (then
POSTGRES_*, see bootstrap.config); skipped when no database is reachable.
"""
import os
import sys
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jobs.key_expiry_alerts import _EXPIRING_API_KEY_SQL, _GRACE_PERIOD_KEY_SQL  # noqa: E402

TZ = "Asia/Kolkata"
ZONE = ZoneInfo(TZ)
LEVELS = [1, 5, 10]


def _url() -> str:
    def setting(name):
        return os.environ.get(f"AUTH_DB_{name}") or os.environ.get(f"POSTGRES_{name}")

    parts = {n: setting(n) for n in ("USER", "PASSWORD", "HOST", "PORT")}
    if not all(parts.values()):
        pytest.skip("no ai4iplatform_auth DB settings (AUTH_DB_* / POSTGRES_*)")
    database = os.environ.get("AUTH_SERVICE_DB_NAME") or "ai4iplatform_auth"
    return f"postgresql+asyncpg://{parts['USER']}:{parts['PASSWORD']}@{parts['HOST']}:{parts['PORT']}/{database}"


@pytest_asyncio.fixture()
async def conn():
    engine = create_async_engine(_url(), connect_args={"timeout": 5})
    try:
        connection = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"could not connect to ai4iplatform_auth: {exc}")
    trans = await connection.begin()
    try:
        if await connection.scalar(text("SELECT to_regclass('api_key')")) is None:
            pytest.skip("api_key doesn't exist; migrate the DB to head first")
        yield connection
    finally:
        await trans.rollback()
        await connection.close()
        await engine.dispose()


@pytest_asyncio.fixture()
async def app(conn):
    """A tenant and an application for the test keys; returns (application_id, today)."""
    tag = uuid.uuid4().hex[:12]
    tenant_id = await conn.scalar(text(
        "INSERT INTO tenants (name, organisation, email, status)"
        " VALUES (:n, 'Expiry SQL Test', :e, 'ACTIVE') RETURNING id"
    ), {"n": f"expiry-sql-{tag}", "e": f"expiry-sql-{tag}@example.com"})
    application_id = await conn.scalar(text(
        "INSERT INTO applications (tenant_id, name) VALUES (:t, 'Expiry SQL App') RETURNING id"
    ), {"t": tenant_id})
    # now() is fixed for the transaction, so "today" is the same for the query.
    today = (await conn.scalar(text("SELECT now()"))).astimezone(ZONE).date()
    return application_id, today


def _local(day: date, days: int, at: time = time(23, 59)) -> datetime:
    return datetime.combine(day + timedelta(days=days), at, tzinfo=ZONE)


async def _key(conn, application_id, name, *, expires_at=None, created_at=None,
               rotated_at=None, rotated_key_expires_at=None, rotated=True, active=True):
    await conn.execute(text(
        "INSERT INTO api_key (application_id, key_name, api_key, is_active, expires_at, created_at,"
        " rotated_key, rotated_at, rotated_key_expires_at)"
        " VALUES (:app, :name, :value, :active, :expires_at, COALESCE(:created_at, now()),"
        " :rotated_key, :rotated_at, :rotated_key_expires_at)"
    ), {
        "app": application_id, "name": name, "value": uuid.uuid4().hex, "active": active,
        "expires_at": expires_at, "created_at": created_at,
        "rotated_key": uuid.uuid4().hex if rotated and rotated_key_expires_at else None,
        "rotated_at": rotated_at, "rotated_key_expires_at": rotated_key_expires_at,
    })


async def _due(conn, sql, application_id) -> dict:
    """key_name -> (days_left, days_before) of this application's candidates."""
    rows = (await conn.execute(sql, {
        "tz": TZ, "levels": LEVELS, "max_level": max(LEVELS), "after_id": 0, "page_size": 500,
    })).mappings()
    return {r["key_name"]: (r["days_left"], r["days_before"])
            for r in rows if r["application_name"] == "Expiry SQL App"}


@pytest.mark.asyncio
async def test_grace_period_levels(conn, app):
    application_id, today = app
    long_ago = _local(today, -30, time(10, 0))

    async def grace(name, days_left, *, rotated_at=long_ago, at=time(23, 59), **kw):
        await _key(conn, application_id, name, rotated_at=rotated_at,
                   rotated_key_expires_at=_local(today, days_left, at), **kw)

    await grace("g11", 11)                  # beyond the largest level
    await grace("g10", 10)
    await grace("g6", 6)                    # 10 missed: caught up with the next level up
    await grace("g1", 1)
    await grace("g0", 0)                    # stops later today
    # Grace of 7 days: the 10 level had already passed at rotation, never sent.
    await grace("short_at_7", 7, rotated_at=_local(today, 0, time(10, 0)))
    await grace("short_at_5", 5, rotated_at=_local(today, -2, time(10, 0)))
    # 00:30 IST on day 6 is 19:00 UTC on day 5: counted in IST it is 6 days -> 10.
    await grace("tz_day6", 6, at=time(0, 30))
    await grace("revoked", 1, active=False)
    # The key itself expires before its old value would: no grace reminder.
    await grace("key_expires_first", 5, expires_at=_local(today, 3))

    assert await _due(conn, _GRACE_PERIOD_KEY_SQL, application_id) == {
        "g10": (10, 10),
        "g6": (6, 10),
        "g1": (1, 1),
        "g0": (0, 1),
        "short_at_5": (5, 5),
        "tz_day6": (6, 10),
    }


@pytest.mark.asyncio
async def test_expiring_api_key_levels(conn, app):
    application_id, today = app
    long_ago = _local(today, -30, time(10, 0))

    async def expiring(name, days_left, *, created_at=long_ago, **kw):
        await _key(conn, application_id, name, created_at=created_at,
                   expires_at=_local(today, days_left), **kw)

    await expiring("e11", 11)
    await expiring("e10", 10)
    await expiring("e6", 6)
    await expiring("e1", 1)
    await expiring("e0", 0)
    # Created with 7 days to live: the 10 level is never sent.
    await expiring("short_at_7", 7, created_at=_local(today, 0, time(10, 0)))
    await expiring("revoked", 1, active=False)
    await _key(conn, application_id, "never_expires", created_at=long_ago)

    assert await _due(conn, _EXPIRING_API_KEY_SQL, application_id) == {
        "e10": (10, 10),
        "e6": (6, 10),
        "e1": (1, 1),
        "e0": (0, 1),
    }
