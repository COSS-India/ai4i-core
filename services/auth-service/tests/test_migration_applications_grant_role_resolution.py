"""Unit tests for the role-resolution helper in the applications-table grant
migration (a9b8c7d6e5f4). No pytest coverage existed for any migration
before this — the module is loaded directly by file path via importlib
since alembic revision files aren't on a normal import path.

Bug scenario this guards against: the migration used to read only
AUTH_DB_USER, while the app itself (AuthSettings.get_database_url) resolves
its connection role through a longer chain — AUTH_DATABASE_URL/DATABASE_URL
first, then AUTH_DB_USER, then POSTGRES_USER, then the literal "postgres"
default. Wherever those two disagreed, the GRANT landed on the wrong role
(or wasn't attempted), the migration still stamped as applied, and every
applications query then failed with InsufficientPrivilegeError with nothing
in the migration log to explain why.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

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
    / "a9b8c7d6e5f4_grant_applications_table_to_app_role.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_grant_migration_under_test", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def migration():
    assert _MIGRATION_PATH.exists(), f"migration file not found at {_MIGRATION_PATH}"
    return _load_migration()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("AUTH_DATABASE_URL", "DATABASE_URL", "AUTH_DB_USER", "POSTGRES_USER"):
        monkeypatch.delenv(var, raising=False)


class TestResolveAppDbRole:
    def test_falls_back_to_literal_postgres_when_nothing_set(self, migration) -> None:
        assert migration._resolve_app_db_role() == "postgres"

    def test_postgres_user_used_when_auth_db_user_unset(self, migration, monkeypatch) -> None:
        monkeypatch.setenv("POSTGRES_USER", "shared_pg_user")
        assert migration._resolve_app_db_role() == "shared_pg_user"

    def test_auth_db_user_takes_priority_over_postgres_user(self, migration, monkeypatch) -> None:
        monkeypatch.setenv("POSTGRES_USER", "shared_pg_user")
        monkeypatch.setenv("AUTH_DB_USER", "ai4i_user")
        assert migration._resolve_app_db_role() == "ai4i_user"

    def test_bug_scenario_auth_database_url_overrides_auth_db_user(self, migration, monkeypatch) -> None:
        """Exact bug: alembic's own env had AUTH_DB_USER=postgres while the
        app's AUTH_DATABASE_URL (when set) actually connects as a different
        role — the old code, reading only AUTH_DB_USER, would grant to the
        wrong role and never notice."""
        monkeypatch.setenv("AUTH_DB_USER", "postgres")
        monkeypatch.setenv(
            "AUTH_DATABASE_URL",
            "postgresql+asyncpg://ai4i_user:secret@localhost:5434/ai4iplatform_auth",
        )
        assert migration._resolve_app_db_role() == "ai4i_user"

    def test_database_url_used_when_auth_database_url_unset(self, migration, monkeypatch) -> None:
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+asyncpg://generic_user:secret@localhost:5434/ai4iplatform_auth",
        )
        assert migration._resolve_app_db_role() == "generic_user"

    def test_auth_database_url_takes_priority_over_database_url(self, migration, monkeypatch) -> None:
        monkeypatch.setenv(
            "AUTH_DATABASE_URL",
            "postgresql+asyncpg://specific_user:secret@localhost:5434/ai4iplatform_auth",
        )
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+asyncpg://generic_user:secret@localhost:5434/other_db",
        )
        assert migration._resolve_app_db_role() == "specific_user"

    def test_url_encoded_username_is_decoded(self, migration, monkeypatch) -> None:
        """An @ or other reserved char in the username is percent-encoded in
        a URL — the resolved role must be the decoded value actually passed
        to GRANT, not the raw encoded form."""
        monkeypatch.setenv(
            "AUTH_DATABASE_URL",
            "postgresql+asyncpg://svc%40prod:secret@localhost:5434/ai4iplatform_auth",
        )
        assert migration._resolve_app_db_role() == "svc@prod"

    def test_never_returns_empty(self, migration) -> None:
        """The old code could return None (falsy) and silently skip the
        grant entirely. The new resolution always names a concrete role."""
        role = migration._resolve_app_db_role()
        assert role
        assert isinstance(role, str)


def _live_connection():
    """A real connection to the local dev Postgres, inside a transaction that
    is always rolled back — never committed. Skips (not fails) when no dev
    DB is reachable, since this is the one test in the suite that needs one:
    _table_owner()'s ownership check is exactly the kind of thing a mock
    can't catch (the original bug was only found by testing against the
    actual table owner on the live DB, not a simplified stand-in for it).
    """
    try:
        from dotenv import dotenv_values
    except ImportError:
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


class TestDowngradeOwnershipGuard:
    """Bug scenario: downgrade() used to unconditionally REVOKE, so if the
    resolved role happens to OWN the table (ownership already implies full
    DML — the upgrade() GRANT was a no-op for it), downgrade() stripped
    privileges this migration never granted, leaving the DB with LESS access
    than before it ran — the exact InsufficientPrivilegeError this migration
    exists to prevent. Runs against the real dev DB (see _live_connection) —
    a mock can't stand in for "does this role actually own this table."
    """

    def test_downgrade_is_a_noop_when_role_owns_the_table(self, migration, monkeypatch) -> None:
        """An owner's access works via ownership regardless of any GRANT/
        REVOKE bookkeeping, so "the owner can still query the table
        afterward" proves nothing either way — REVOKE on an owner is
        harmless but also pointless. The only real signal that downgrade()
        actually skipped the REVOKE (not just that it was harmless) is that
        no REVOKE statement was issued at all — checked here by spying on
        op.execute rather than inferring it from downstream behavior.
        """
        from alembic.operations import Operations
        from alembic.runtime.migration import MigrationContext

        conn = _live_connection()
        trans = conn.begin()
        try:
            owner = conn.exec_driver_sql(
                "SELECT tableowner FROM pg_tables WHERE tablename = 'applications'"
            ).scalar()
            assert owner, "applications table not found on this dev DB"
            monkeypatch.setenv("AUTH_DB_USER", owner)

            executed = []
            monkeypatch.setattr(migration.op, "execute", lambda sql: executed.append(sql))

            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

            revoke_statements = [s for s in executed if "REVOKE" in s]
            assert revoke_statements == [], (
                f"downgrade() issued REVOKE for the table owner: {revoke_statements}"
            )
        finally:
            trans.rollback()
            conn.close()

    def test_downgrade_revokes_when_role_is_not_the_owner(self, migration, monkeypatch) -> None:
        from alembic.operations import Operations
        from alembic.runtime.migration import MigrationContext

        conn = _live_connection()
        trans = conn.begin()
        try:
            owner = conn.exec_driver_sql(
                "SELECT tableowner FROM pg_tables WHERE tablename = 'applications'"
            ).scalar()
            non_owner_role = "ai4i_user" if owner != "ai4i_user" else "postgres"
            grantee_exists = conn.exec_driver_sql(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (non_owner_role,)
            ).scalar()
            if not grantee_exists:
                pytest.skip(f"role {non_owner_role!r} does not exist on this dev DB")

            conn.exec_driver_sql(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON applications TO "{non_owner_role}"'
            )
            monkeypatch.setenv("AUTH_DB_USER", non_owner_role)

            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

            remaining = conn.exec_driver_sql(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE table_name = 'applications' AND grantee = %s",
                (non_owner_role,),
            ).fetchall()
            assert remaining == [], f"expected no privileges left for {non_owner_role!r}, found {remaining}"
        finally:
            trans.rollback()
            conn.close()
