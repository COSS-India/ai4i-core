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
