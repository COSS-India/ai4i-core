"""Tests for b8a1957cd6a3 (revoke current-only-revoked keys, drop api_key_revoked_at).

Runs against the real dev DB inside a transaction that is always rolled back
(same pattern as test_migration_backfill_unconfigured_key_exhaustion.py). The
column is added first when absent, so the test runs whether or not the DB is
already migrated. Redis entries the test writes are deleted in teardown.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

_ALEMBIC_DIR = Path(__file__).resolve().parents[3] / "infrastructure" / "databases" / "migrations" / "postgres" / "alembic"
_MIGRATION_PATH = _ALEMBIC_DIR / "versions" / "ai4iplatform_auth" / "b8a1957cd6a3_drop_api_key_revoked_at_from_api_key.py"

_APP_ID = -9002
_CURRENT_ONLY_REVOKED = "test_migr_b8a1_current_revoked1"
_CURRENT_ONLY_REVOKED_PREV = "test_migr_b8a1_previous_value01"
_UNTOUCHED = "test_migr_b8a1_untouched_key001"
_ALREADY_REVOKED = "test_migr_b8a1_already_revoked1"


@pytest.fixture()
def migration():
    sys.path.insert(0, str(_ALEMBIC_DIR))  # the migration imports migration_registry
    spec = importlib.util.spec_from_file_location("_drop_revoked_at_under_test", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _live_connection():
    if dotenv_values is None:
        pytest.skip("python-dotenv not installed")
    env = dotenv_values(_ALEMBIC_DIR / ".env")
    required = ("AUTH_DB_HOST", "AUTH_DB_PORT", "AUTH_DB_USER", "AUTH_DB_PASSWORD", "AUTH_DB_NAME")
    if any(not env.get(k) for k in required):
        pytest.skip("alembic .env missing required AUTH_DB_* vars")

    from sqlalchemy import create_engine

    url = (
        f"postgresql://{env['AUTH_DB_USER']}:{env['AUTH_DB_PASSWORD']}"
        f"@{env['AUTH_DB_HOST']}:{env['AUTH_DB_PORT']}/{env['AUTH_DB_NAME']}"
    )
    try:
        return create_engine(url).connect()
    except Exception as exc:
        pytest.skip(f"could not connect to dev DB: {exc}")


def _seed(conn):
    conn.exec_driver_sql("ALTER TABLE api_key ADD COLUMN IF NOT EXISTS api_key_revoked_at timestamptz")
    conn.exec_driver_sql(f"DELETE FROM api_key WHERE application_id = {_APP_ID}")
    conn.exec_driver_sql(f"DELETE FROM applications WHERE id = {_APP_ID}")
    conn.execute(text(
        "INSERT INTO applications (id, tenant_id, name, status, allocated_budget) "
        "VALUES (:id, 1, 'MigrationTestB8a1', 'ACTIVE', NULL)"
    ), {"id": _APP_ID})
    for api_key, rotated_key, revoked_at, is_active in (
        (_CURRENT_ONLY_REVOKED, _CURRENT_ONLY_REVOKED_PREV, "now()", True),
        (_UNTOUCHED, None, "NULL", True),
        (_ALREADY_REVOKED, None, "now()", False),
    ):
        conn.execute(text(
            "INSERT INTO api_key (application_id, key_name, api_key, rotated_key, rotated_key_expires_at, "
            " api_key_revoked_at, permissions, is_active) "
            f"VALUES (:app, :name, :key, :rotated, now() + interval '1 day', {revoked_at}, '{{}}', :active)"
        ), {"app": _APP_ID, "name": api_key, "key": api_key, "rotated": rotated_key, "active": is_active})


def _run_upgrade(migration, conn):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    with Operations.context(MigrationContext.configure(conn)):
        migration.upgrade()


def _is_active(conn, api_key):
    return conn.execute(text("SELECT is_active FROM api_key WHERE api_key = :k"), {"k": api_key}).scalar()


def test_current_only_revoked_key_is_revoked_and_column_dropped(migration, monkeypatch) -> None:
    monkeypatch.setattr(migration, "get_redis_client", lambda: None)
    conn = _live_connection()
    trans = conn.begin()
    try:
        _seed(conn)
        _run_upgrade(migration, conn)

        assert _is_active(conn, _CURRENT_ONLY_REVOKED) is False
        assert _is_active(conn, _UNTOUCHED) is True
        assert _is_active(conn, _ALREADY_REVOKED) is False
        assert conn.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'api_key' AND column_name = 'api_key_revoked_at'"
        )).scalar() == 0
    finally:
        trans.rollback()
        conn.close()


def test_revoked_key_values_are_removed_from_redis(migration) -> None:
    from migration_registry import get_redis_client

    redis_client = get_redis_client()
    if redis_client is None:
        pytest.skip("dev Redis unreachable")
    entries = [f"auth:apikey:{v}" for v in (_CURRENT_ONLY_REVOKED, _CURRENT_ONLY_REVOKED_PREV, _UNTOUCHED)]
    conn = _live_connection()
    trans = conn.begin()
    try:
        _seed(conn)
        for entry in entries:
            redis_client.hset(entry, mapping={"application_id": str(_APP_ID)})
        _run_upgrade(migration, conn)

        assert redis_client.exists(entries[0]) == 0
        assert redis_client.exists(entries[1]) == 0
        assert redis_client.exists(entries[2]) == 1
    finally:
        redis_client.delete(*entries)
        redis_client.close()
        trans.rollback()
        conn.close()
