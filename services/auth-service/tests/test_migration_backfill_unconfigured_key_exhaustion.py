"""Unit tests for the budget-exhausted backfill migration (f3a9b1c7d2e6).

Runs against the real dev DB (same pattern as
test_migration_application_permissions_seed.py) inside a transaction that
is always rolled back — the eligibility filter depends on live NULL vs.
non-NULL cached_data rows and Postgres's own ANY(:ids) semantics, which a
mock can't stand in for. The Redis half is exercised against the real dev
Redis too (same env the migration itself reads), with keys the test
creates removed again in its own teardown since Redis writes aren't part
of the SQL transaction and don't roll back with it.
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

_ALEMBIC_ENV_PATH = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "databases"
    / "migrations"
    / "postgres"
    / "alembic"
    / ".env"
)

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "databases"
    / "migrations"
    / "postgres"
    / "alembic"
    / "versions"
    / "ai4iplatform_auth"
    / "f3a9b1c7d2e6_backfill_unconfigured_key_exhaustion.py"
)

_TEST_APPLICATION_ID = -9001
_KEY_NULL_CACHED = "test_migr_null_cached_data_0001"
_KEY_REAL_CACHED = "test_migr_real_cached_data_0001"
_KEY_ALREADY_CONFIGURED = "test_migr_already_configured_01"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_backfill_migration_under_test", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def migration():
    assert _MIGRATION_PATH.exists(), f"migration file not found at {_MIGRATION_PATH}"
    return _load_migration()


def _live_connection():
    if dotenv_values is None:
        pytest.skip("python-dotenv not installed")
    if not _ALEMBIC_ENV_PATH.exists():
        pytest.skip(f"no alembic .env at {_ALEMBIC_ENV_PATH}")
    env = dotenv_values(_ALEMBIC_ENV_PATH)
    required = ("AUTH_DB_HOST", "AUTH_DB_PORT", "AUTH_DB_USER", "AUTH_DB_PASSWORD", "AUTH_DB_NAME")
    if any(not env.get(k) for k in required):
        pytest.skip("alembic .env missing required AUTH_DB_* vars")

    from sqlalchemy import create_engine

    url = (
        f"postgresql://{env['AUTH_DB_USER']}:{env['AUTH_DB_PASSWORD']}"
        f"@{env['AUTH_DB_HOST']}:{env['AUTH_DB_PORT']}/{env['AUTH_DB_NAME']}"
    )
    try:
        engine = create_engine(url)
        conn = engine.connect()
    except Exception as exc:
        pytest.skip(f"could not connect to dev DB: {exc}")
    return conn


def _run_upgrade(migration, conn):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        migration.upgrade()


def _redis_or_skip(migration):
    client = migration._redis_client()
    if client is None:
        pytest.skip("dev Redis unreachable")
    return client


class TestEnvHostPort:
    """`_env_host_port` is a pure function - no DB/Redis needed. Covers the
    exact regression flagged in review: REDIS_PORT's Kubernetes-injected
    tcp://<ip>:<port> must never override an explicitly-set REDIS_HOST,
    only ever supply a fallback host when REDIS_HOST is unset."""

    def test_plain_int_port_is_unaffected(self, migration, monkeypatch) -> None:
        monkeypatch.setenv("REDIS_HOST", "auth-redis-master")
        monkeypatch.setenv("REDIS_PORT", "6380")
        assert migration._env_host_port("REDIS_HOST", "REDIS_PORT", 6379) == (
            "auth-redis-master",
            6380,
        )

    def test_k8s_tcp_port_does_not_clobber_an_explicit_host(self, migration, monkeypatch) -> None:
        monkeypatch.setenv("REDIS_HOST", "auth-redis-master")
        monkeypatch.setenv("REDIS_PORT", "tcp://10.100.206.16:6379")
        assert migration._env_host_port("REDIS_HOST", "REDIS_PORT", 6379) == (
            "auth-redis-master",
            6379,
        )

    def test_k8s_tcp_port_supplies_the_host_when_none_is_set(self, migration, monkeypatch) -> None:
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.setenv("REDIS_PORT", "tcp://10.100.206.16:6379")
        assert migration._env_host_port("REDIS_HOST", "REDIS_PORT", 6379) == (
            "10.100.206.16",
            6379,
        )

    def test_neither_var_set_falls_back_to_localhost_and_default_port(
        self, migration, monkeypatch
    ) -> None:
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)
        assert migration._env_host_port("REDIS_HOST", "REDIS_PORT", 6379) == (
            "localhost",
            6379,
        )


class TestBackfillEligibility:
    def test_null_cached_data_is_excluded_but_real_cached_data_is_backfilled(
        self, migration
    ) -> None:
        """The exact bug this fixes: a plain COALESCE would manufacture a
        fabricated {"budget-exhausted": "1"} snapshot for a row that's
        cached_data IS NULL by design (fail-closed, 401) — turning it into
        a "valid but exhausted" (429) row instead, which is worse. Matching
        APIKeyRepository._active_key_conditions(require_cached_data=True)
        exactly means the NULL row must come back untouched."""
        conn = _live_connection()
        trans = conn.begin()
        try:
            conn.exec_driver_sql(
                f"DELETE FROM api_key WHERE api_key IN "
                f"('{_KEY_NULL_CACHED}', '{_KEY_REAL_CACHED}')"
            )
            conn.exec_driver_sql(
                f"DELETE FROM applications WHERE id = {_TEST_APPLICATION_ID}"
            )
            conn.execute(text(
                "INSERT INTO applications (id, tenant_id, name, status, allocated_budget) "
                "VALUES (:id, 1, 'MigrationTestApp', 'ACTIVE', NULL)"
            ), {"id": _TEST_APPLICATION_ID})
            conn.execute(text(
                "INSERT INTO api_key "
                "(application_id, key_name, api_key, allocated_percentage, allocated_budget, "
                " permissions, is_active, cached_data) "
                "VALUES (:app_id, 'NullCached', :k1, NULL, NULL, '{}', true, NULL)"
            ), {"app_id": _TEST_APPLICATION_ID, "k1": _KEY_NULL_CACHED})
            conn.execute(text(
                "INSERT INTO api_key "
                "(application_id, key_name, api_key, allocated_percentage, allocated_budget, "
                " permissions, is_active, cached_data) "
                "VALUES (:app_id, 'RealCached', :k2, NULL, NULL, '{}', true, "
                " '{\"application_id\": \"-9001\", \"tenant_id\": \"1\"}'::jsonb)"
            ), {"app_id": _TEST_APPLICATION_ID, "k2": _KEY_REAL_CACHED})

            _run_upgrade(migration, conn)

            null_row = conn.execute(text(
                "SELECT cached_data FROM api_key WHERE api_key = :k"
            ), {"k": _KEY_NULL_CACHED}).scalar()
            assert null_row is None

            real_row = conn.execute(text(
                "SELECT cached_data FROM api_key WHERE api_key = :k"
            ), {"k": _KEY_REAL_CACHED}).scalar()
            assert real_row["budget-exhausted"] == "1"
            assert real_row["tenant_id"] == "1"  # merged in, not overwritten
        finally:
            trans.rollback()
            conn.close()

    def test_already_configured_key_is_left_alone(self, migration) -> None:
        """allocated_budget IS NOT NULL — outside the eligibility filter
        entirely, regardless of whatever its cached_data says."""
        conn = _live_connection()
        trans = conn.begin()
        try:
            conn.exec_driver_sql(
                f"DELETE FROM api_key WHERE api_key = '{_KEY_ALREADY_CONFIGURED}'"
            )
            conn.exec_driver_sql(
                f"DELETE FROM applications WHERE id = {_TEST_APPLICATION_ID}"
            )
            conn.execute(text(
                "INSERT INTO applications (id, tenant_id, name, status, allocated_budget) "
                "VALUES (:id, 1, 'MigrationTestApp2', 'ACTIVE', 50000)"
            ), {"id": _TEST_APPLICATION_ID})
            conn.execute(text(
                "INSERT INTO api_key "
                "(application_id, key_name, api_key, allocated_percentage, allocated_budget, "
                " permissions, is_active, cached_data) "
                "VALUES (:app_id, 'AlreadyConfigured', :k, 50, 25000, '{}', true, "
                " '{\"application_id\": \"-9001\"}'::jsonb)"
            ), {"app_id": _TEST_APPLICATION_ID, "k": _KEY_ALREADY_CONFIGURED})

            _run_upgrade(migration, conn)

            row = conn.execute(text(
                "SELECT cached_data FROM api_key WHERE api_key = :k"
            ), {"k": _KEY_ALREADY_CONFIGURED}).scalar()
            assert "budget-exhausted" not in row
        finally:
            trans.rollback()
            conn.close()


class TestBackfillIdempotency:
    def test_running_twice_does_not_error_or_change_the_result(self, migration) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            conn.exec_driver_sql(
                f"DELETE FROM api_key WHERE api_key = '{_KEY_REAL_CACHED}'"
            )
            conn.exec_driver_sql(
                f"DELETE FROM applications WHERE id = {_TEST_APPLICATION_ID}"
            )
            conn.execute(text(
                "INSERT INTO applications (id, tenant_id, name, status, allocated_budget) "
                "VALUES (:id, 1, 'MigrationTestApp3', 'ACTIVE', NULL)"
            ), {"id": _TEST_APPLICATION_ID})
            conn.execute(text(
                "INSERT INTO api_key "
                "(application_id, key_name, api_key, allocated_percentage, allocated_budget, "
                " permissions, is_active, cached_data) "
                "VALUES (:app_id, 'RealCached', :k, NULL, NULL, '{}', true, "
                " '{\"application_id\": \"-9001\"}'::jsonb)"
            ), {"app_id": _TEST_APPLICATION_ID, "k": _KEY_REAL_CACHED})

            _run_upgrade(migration, conn)
            _run_upgrade(migration, conn)

            row = conn.execute(text(
                "SELECT cached_data FROM api_key WHERE api_key = :k"
            ), {"k": _KEY_REAL_CACHED}).scalar()
            assert row["budget-exhausted"] == "1"
        finally:
            trans.rollback()
            conn.close()


class TestBackfillPushesToRedisWhenResident:
    def test_a_key_currently_cached_in_redis_gets_patched_too(self, migration) -> None:
        """Comment: DB-only is inert for exactly the keys that exhibit the
        bug (an actively-used key stays resident in Redis for up to
        api_key_expire_days). A key present in Redis at migration time must
        have budget-exhausted pushed onto its live hash too, not just its
        DB snapshot."""
        redis_client = _redis_or_skip(migration)
        redis_key = f"{migration._REDIS_API_KEY_PREFIX}{_KEY_REAL_CACHED}"
        conn = _live_connection()
        trans = conn.begin()
        try:
            conn.exec_driver_sql(
                f"DELETE FROM api_key WHERE api_key = '{_KEY_REAL_CACHED}'"
            )
            conn.exec_driver_sql(
                f"DELETE FROM applications WHERE id = {_TEST_APPLICATION_ID}"
            )
            conn.execute(text(
                "INSERT INTO applications (id, tenant_id, name, status, allocated_budget) "
                "VALUES (:id, 1, 'MigrationTestApp4', 'ACTIVE', NULL)"
            ), {"id": _TEST_APPLICATION_ID})
            conn.execute(text(
                "INSERT INTO api_key "
                "(application_id, key_name, api_key, allocated_percentage, allocated_budget, "
                " permissions, is_active, cached_data) "
                "VALUES (:app_id, 'RealCached', :k, NULL, NULL, '{}', true, "
                " '{\"application_id\": \"-9001\"}'::jsonb)"
            ), {"app_id": _TEST_APPLICATION_ID, "k": _KEY_REAL_CACHED})

            redis_client.hset(redis_key, mapping={"application_id": "-9001"})
            try:
                _run_upgrade(migration, conn)
                assert redis_client.hget(redis_key, "budget-exhausted") == "1"
            finally:
                redis_client.delete(redis_key)
        finally:
            trans.rollback()
            conn.close()
            redis_client.close()

    def test_a_key_absent_from_redis_is_not_fabricated_there(self, migration) -> None:
        """patch_api_key_cache_field's own contract — HSET only if the hash
        already exists — mirrored here: a key that was never in Redis at
        all (Redis miss, or never actively used) must not have a Redis
        entry manufactured for it as a side effect of this migration."""
        redis_client = _redis_or_skip(migration)
        redis_key = f"{migration._REDIS_API_KEY_PREFIX}{_KEY_REAL_CACHED}"
        conn = _live_connection()
        trans = conn.begin()
        try:
            conn.exec_driver_sql(
                f"DELETE FROM api_key WHERE api_key = '{_KEY_REAL_CACHED}'"
            )
            conn.exec_driver_sql(
                f"DELETE FROM applications WHERE id = {_TEST_APPLICATION_ID}"
            )
            conn.execute(text(
                "INSERT INTO applications (id, tenant_id, name, status, allocated_budget) "
                "VALUES (:id, 1, 'MigrationTestApp5', 'ACTIVE', NULL)"
            ), {"id": _TEST_APPLICATION_ID})
            conn.execute(text(
                "INSERT INTO api_key "
                "(application_id, key_name, api_key, allocated_percentage, allocated_budget, "
                " permissions, is_active, cached_data) "
                "VALUES (:app_id, 'RealCached', :k, NULL, NULL, '{}', true, "
                " '{\"application_id\": \"-9001\"}'::jsonb)"
            ), {"app_id": _TEST_APPLICATION_ID, "k": _KEY_REAL_CACHED})

            redis_client.delete(redis_key)
            _run_upgrade(migration, conn)
            assert redis_client.exists(redis_key) == 0
        finally:
            trans.rollback()
            conn.close()
            redis_client.close()
