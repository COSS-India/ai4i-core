"""Tests for the creation_type backfill migration (e7a1b2c3d4f5).

Runs against the real dev DB (same pattern as
test_migration_backfill_unconfigured_key_exhaustion.py) inside a transaction
that is always rolled back — the classification hinges on Postgres's
per-transaction now() making a self-registered user's users/credentials
created_at identical, which a mock can't stand in for.
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
    _ALEMBIC_DIR
    / "versions"
    / "ai4iplatform_auth"
    / "e7a1b2c3d4f5_backfill_admin_created_users_creation_type.py"
)

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"
T0 = "2026-05-10 10:00:00+00"
T_LATER = "2026-05-11 09:30:00+00"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_creation_type_backfill_under_test", _MIGRATION_PATH)
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


def _insert_user(conn, *, creation_type, created_by=None, creds_at=None, role=None) -> str:
    user_id = str(uuid.uuid4())
    conn.execute(text(
        "INSERT INTO users (id, email, username, is_active, creation_type, created_by, created_at) "
        "VALUES (:id, :email, :username, true, CAST(:ct AS creation_type_enum), "
        "CAST(:cb AS uuid), CAST(:at AS timestamptz))"
    ), {
        "id": user_id,
        "email": f"test-migr-{user_id}@example.invalid",
        "username": f"test_migr_{user_id[:12]}",
        "ct": creation_type,
        "cb": created_by,
        "at": T0,
    })
    if creds_at is not None:
        conn.execute(text(
            "INSERT INTO user_credentials (user_id, password_hash, password_salt, created_at) "
            "VALUES (:id, 'x', 'x', CAST(:at AS timestamptz))"
        ), {"id": user_id, "at": creds_at})
    if role is not None:
        conn.execute(text(
            "INSERT INTO user_role (user_id, role_id) "
            "SELECT :id, id FROM roles WHERE name = :role"
        ), {"id": user_id, "role": role})
    return user_id


def _creation_type(conn, user_id: str) -> str:
    return conn.execute(
        text("SELECT creation_type::text FROM users WHERE id = :id"), {"id": user_id}
    ).scalar()


class TestCreationTypeBackfill:
    def test_classifies_each_account_origin(self, migration) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            self_registered = _insert_user(conn, creation_type="default", creds_at=T0, role="USER")
            provisioned_pending = _insert_user(conn, creation_type="default", role="TENANT ADMIN")
            provisioned_activated = _insert_user(conn, creation_type="default", creds_at=T_LATER, role="USER")
            google = _insert_user(conn, creation_type="google", role="USER")
            seeded_admin = _insert_user(
                conn, creation_type="default", created_by=SEEDER_ID, creds_at=T0, role="ADMIN"
            )
            seeded_guest = _insert_user(
                conn, creation_type="default", created_by=SEEDER_ID, creds_at=T0, role="GUEST"
            )
            already_tenant = _insert_user(conn, creation_type="tenant", creds_at=T_LATER, role="USER")

            _run_upgrade(migration, conn)

            assert _creation_type(conn, self_registered) == "default"
            assert _creation_type(conn, provisioned_pending) == "tenant"
            assert _creation_type(conn, provisioned_activated) == "tenant"
            assert _creation_type(conn, google) == "google"
            assert _creation_type(conn, seeded_admin) == "tenant"
            assert _creation_type(conn, seeded_guest) == "default"
            assert _creation_type(conn, already_tenant) == "tenant"
        finally:
            trans.rollback()
            conn.close()
