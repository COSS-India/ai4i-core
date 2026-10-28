"""Tests for the users.activated_at migration (ba0818f032cd).

Runs against the real dev DB inside a transaction that is always rolled back
(same pattern as test_migration_backfill_admin_created_creation_type.py). If
the dev DB is already migrated, the column is dropped first inside that
transaction so upgrade() runs from the pre-migration shape.
"""

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

_ALEMBIC_DIR = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "databases"
    / "migrations"
    / "postgres"
    / "alembic"
)
_ALEMBIC_ENV_PATH = _ALEMBIC_DIR / ".env"
_MIGRATION_PATH = (
    _ALEMBIC_DIR / "versions" / "ai4iplatform_auth" / "ba0818f032cd_add_users_activated_at.py"
)

T_CREATED = "2026-05-10 10:00:00+00"
T_LOGIN = "2026-06-01 08:00:00+00"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_activated_at_under_test", _MIGRATION_PATH)
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

    conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS activated_at"))
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        migration.upgrade()


def _insert_user(conn, *, creation_type, is_active, last_login=None, with_creds=False) -> str:
    user_id = str(uuid.uuid4())
    conn.execute(text(
        "INSERT INTO users (id, email, username, is_active, creation_type, created_at, last_login) "
        "VALUES (:id, :email, :username, :active, CAST(:ct AS creation_type_enum), "
        "CAST(:at AS timestamptz), CAST(:login AS timestamptz))"
    ), {
        "id": user_id,
        "email": f"test-migr-{user_id}@example.invalid",
        "username": f"test_migr_{user_id[:12]}",
        "active": is_active,
        "ct": creation_type,
        "at": T_CREATED,
        "login": last_login,
    })
    if with_creds:
        conn.execute(text(
            "INSERT INTO user_credentials (user_id, password_hash, password_salt) "
            "VALUES (:id, 'x', 'x')"
        ), {"id": user_id})
    return user_id


def _activated_at(conn, user_id: str):
    return conn.execute(
        text("SELECT activated_at FROM users WHERE id = :id"), {"id": user_id}
    ).scalar()


class TestActivatedAtBackfill:
    def test_classifies_each_account_state(self, migration) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            # The reported bug: password stored at signup, email never verified.
            unverified_signup = _insert_user(
                conn, creation_type="default", is_active=False, with_creds=True
            )
            active_signup = _insert_user(
                conn, creation_type="default", is_active=True, with_creds=True
            )
            suspended_signup = _insert_user(
                conn, creation_type="default", is_active=False,
                last_login=T_LOGIN, with_creds=True,
            )
            suspended_google = _insert_user(
                conn, creation_type="google", is_active=False, last_login=T_LOGIN
            )
            pending_invite = _insert_user(conn, creation_type="tenant", is_active=False)
            suspended_invite = _insert_user(
                conn, creation_type="tenant", is_active=False, with_creds=True
            )

            _run_upgrade(migration, conn)

            assert _activated_at(conn, unverified_signup) is None
            assert _activated_at(conn, pending_invite) is None
            assert _activated_at(conn, active_signup) is not None
            assert _activated_at(conn, suspended_signup).isoformat().startswith("2026-06-01")
            assert _activated_at(conn, suspended_google) is not None
            assert _activated_at(conn, suspended_invite).isoformat().startswith("2026-05-10")
        finally:
            trans.rollback()
            conn.close()
