"""Unit tests for the application-permissions seed migration (c2d3e4f5a6b7).

Bug scenario: the permissions INSERT was guarded on "id exists OR name
exists" — so on a drifted DB where the migration's preferred id (e.g. 43) is
already claimed by some unrelated permission, the INSERT silently skipped.
The role_permission grant right after it joins by NAME only, so with no row
named "application.create" ever created, that join matched nothing too —
zero rows inserted, zero errors raised, migration reports success while
granting nothing. Runs against the real dev DB (a mock can't stand in for
"is this id already taken by an unrelated row" — that's a live constraint,
not a Python condition) inside a transaction that is always rolled back.
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
    / "c2d3e4f5a6b7_grant_application_permissions.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_perm_migration_under_test", _MIGRATION_PATH)
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


class TestPermissionSeedIdempotency:
    def test_running_twice_on_a_clean_db_grants_exactly_once(self, migration) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            # Start clean: remove any prior application.* rows so this test
            # exercises a true from-scratch seed, not whatever this dev DB
            # already had from earlier work in this session.
            conn.execute(text(
                "DELETE FROM role_permission WHERE permission_id IN "
                "(SELECT id FROM permissions WHERE name LIKE :pattern)"
            ), {"pattern": "application.%"})
            conn.execute(
                text("DELETE FROM permissions WHERE name LIKE :pattern"),
                {"pattern": "application.%"},
            )

            _run_upgrade(migration, conn)
            _run_upgrade(migration, conn)  # idempotent re-run must not error or duplicate

            rows = conn.execute(text(
                "SELECT p.name, r.name FROM role_permission rp "
                "JOIN permissions p ON p.id = rp.permission_id "
                "JOIN roles r ON r.id = rp.role_id "
                "WHERE p.name LIKE :pattern"
            ), {"pattern": "application.%"}).fetchall()
            by_name = {}
            for perm_name, role_name in rows:
                by_name.setdefault(perm_name, set()).add(role_name)

            assert by_name.get("application.create") == {"ADMIN", "TENANT ADMIN"}
            assert by_name.get("application.read") == {"ADMIN", "TENANT ADMIN"}
            assert by_name.get("application.update") == {"ADMIN", "TENANT ADMIN"}
        finally:
            trans.rollback()
            conn.close()


class TestPermissionSeedDriftedId:
    """The exact bug scenario: id 43 already taken by an unrelated permission."""

    def test_id_collision_fails_loudly_instead_of_silently_granting_nothing(
        self, migration
    ) -> None:
        from sqlalchemy.exc import IntegrityError

        conn = _live_connection()
        trans = conn.begin()
        try:
            conn.execute(text(
                "DELETE FROM role_permission WHERE permission_id IN "
                "(SELECT id FROM permissions WHERE name LIKE :pattern)"
            ), {"pattern": "application.%"})
            conn.execute(
                text("DELETE FROM permissions WHERE name LIKE :pattern"),
                {"pattern": "application.%"},
            )
            conn.exec_driver_sql("DELETE FROM permissions WHERE id = 43")

            # Simulate drift: id 43 already belongs to some unrelated
            # permission on this DB, from a different feature entirely.
            conn.exec_driver_sql(
                "INSERT INTO permissions (id, name, resource, action) "
                "VALUES (43, 'some_other_feature.action', 'some_other_feature', 'action')"
            )

            # A failed statement aborts the whole Postgres transaction (any
            # later statement on it errors with "current transaction is
            # aborted" until rolled back) — run the migration in a SAVEPOINT
            # so only that nested piece rolls back, leaving the outer
            # transaction usable for the assertion below.
            savepoint = conn.begin_nested()
            try:
                with pytest.raises(IntegrityError):
                    _run_upgrade(migration, conn)
            finally:
                savepoint.rollback()

            # The bug this replaces: the old double guard would let this
            # complete with ZERO rows changed and no error. Assert that
            # didn't happen — nothing named application.create exists,
            # which is expected (the whole point is it must fail, not
            # silently "succeed" while granting nothing).
            remaining = conn.exec_driver_sql(
                "SELECT count(*) FROM permissions WHERE name = 'application.create'"
            ).scalar()
            assert remaining == 0
        finally:
            trans.rollback()
            conn.close()
