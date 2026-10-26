"""Tests for the self-registered role reset migration (a7c3e9f15b28).

Runs against the real dev DB inside a transaction that is always rolled back
(same pattern as test_migration_backfill_admin_created_creation_type.py).
Both migrations run in chain order — e7a1b2c3d4f5 re-labels admin-created
users first — so an admin-created user still stored as 'default' must come
out of the pair with its roles intact.
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
_VERSIONS = _ALEMBIC_DIR / "versions" / "ai4iplatform_auth"
_BACKFILL_PATH = _VERSIONS / "e7a1b2c3d4f5_backfill_admin_created_users_creation_type.py"
_RESET_PATH = _VERSIONS / "a7c3e9f15b28_reset_self_registered_users_to_user_role.py"

T0 = "2026-05-10 10:00:00+00"
T_LATER = "2026-05-11 09:30:00+00"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def migrations():
    for path in (_BACKFILL_PATH, _RESET_PATH):
        assert path.exists(), f"migration file not found at {path}"
    return (
        _load(_BACKFILL_PATH, "_backfill_under_test"),
        _load(_RESET_PATH, "_role_reset_under_test"),
    )


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


def _run_upgrades(migrations, conn):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        for migration in migrations:
            migration.upgrade()


def _insert_user(
    conn, *, creation_type, roles=(), creds_at=T0, is_active=True, is_delete=False,
    created_at=T0, username=None,
) -> str:
    user_id = str(uuid.uuid4())
    conn.execute(text(
        "INSERT INTO users (id, email, username, is_active, is_delete, creation_type, created_at) "
        "VALUES (:id, :email, :username, :active, :deleted, CAST(:ct AS creation_type_enum), "
        "CAST(:at AS timestamptz))"
    ), {
        "id": user_id,
        "email": f"test-reset-{user_id}@example.invalid",
        "username": username or f"test_reset_{user_id[:12]}",
        "active": is_active,
        "deleted": is_delete,
        "ct": creation_type,
        "at": created_at,
    })
    if creds_at is not None:
        conn.execute(text(
            "INSERT INTO user_credentials (user_id, password_hash, password_salt, created_at) "
            "VALUES (:id, 'x', 'x', CAST(:at AS timestamptz))"
        ), {"id": user_id, "at": creds_at})
    for role in roles:
        inserted = conn.execute(text(
            "INSERT INTO user_role (user_id, role_id) "
            "SELECT :id, id FROM roles WHERE name = :role RETURNING role_id"
        ), {"id": user_id, "role": role}).fetchall()
        assert inserted, f"role {role!r} not found in roles table"
    return user_id


def _roles(conn, user_id: str) -> list[str]:
    return [
        row[0] for row in conn.execute(text(
            "SELECT r.name FROM user_role ur JOIN roles r ON r.id = ur.role_id "
            "WHERE ur.user_id = :id ORDER BY r.name"
        ), {"id": user_id})
    ]


class TestResetSelfRegisteredRoles:
    def test_old_self_registered_grants_are_reset_to_user(self, migrations) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            # The reported case: an email signup that was given USAGE VIEWER
            # before the lock, now shown with a disabled role control.
            usage_viewer_signup = _insert_user(conn, creation_type="default", roles=("USAGE VIEWER",))
            google_moderator = _insert_user(conn, creation_type="google", creds_at=None, roles=("USER", "MODERATOR"))
            inactive_admin_signup = _insert_user(
                conn, creation_type="default", roles=("USER", "ADMIN"), is_active=False
            )
            deleted_signup = _insert_user(conn, creation_type="default", roles=("MODERATOR",), is_delete=True)
            plain_signup = _insert_user(conn, creation_type="default", roles=("USER",))
            tenant_moderator = _insert_user(
                conn, creation_type="tenant", creds_at=T_LATER, roles=("USER", "MODERATOR")
            )
            # Admin-created but stored as 'default' (2026-04-29 → 05-22):
            # the backfill must re-label it before the reset runs.
            legacy_institution_admin = _insert_user(
                conn, creation_type="default", creds_at=T_LATER, roles=("TENANT ADMIN",)
            )

            _run_upgrades(migrations, conn)

            assert _roles(conn, usage_viewer_signup) == ["USER"]
            assert _roles(conn, google_moderator) == ["USER"]
            assert _roles(conn, inactive_admin_signup) == ["USER"]
            assert _roles(conn, deleted_signup) == []
            assert _roles(conn, plain_signup) == ["USER"]
            assert _roles(conn, tenant_moderator) == ["MODERATOR", "USER"]
            assert _roles(conn, legacy_institution_admin) == ["TENANT ADMIN"]
        finally:
            trans.rollback()
            conn.close()

    def test_seeded_guest_keeps_guest_role(self, migrations) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            guest_id = conn.execute(text("SELECT id FROM users WHERE username = 'guest'")).scalar()
            if guest_id is None:
                guest_id = _insert_user(conn, creation_type="default", roles=("GUEST",), username="guest")
            else:
                guest_id = str(guest_id)
                conn.execute(text("DELETE FROM user_role WHERE user_id = :id"), {"id": guest_id})
                conn.execute(text(
                    "INSERT INTO user_role (user_id, role_id) SELECT :id, id FROM roles WHERE name = 'GUEST'"
                ), {"id": guest_id})

            _run_upgrades(migrations, conn)

            assert _roles(conn, guest_id) == ["GUEST"]
        finally:
            trans.rollback()
            conn.close()

    def test_keeps_admin_on_oldest_self_registered_admin_when_none_other_remains(
        self, migrations
    ) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            # Simulate an environment whose only active admins are self-registered.
            conn.execute(text(
                "DELETE FROM user_role WHERE role_id = (SELECT id FROM roles WHERE name = 'ADMIN')"
            ))
            older = _insert_user(
                conn, creation_type="default", roles=("USER", "ADMIN", "MODERATOR"),
                created_at="2026-05-01 00:00:00+00", creds_at="2026-05-01 00:00:00+00",
            )
            newer = _insert_user(
                conn, creation_type="default", roles=("USER", "ADMIN"),
                created_at="2026-06-01 00:00:00+00", creds_at="2026-06-01 00:00:00+00",
            )

            _run_upgrades(migrations, conn)

            assert _roles(conn, older) == ["ADMIN", "USER"]
            assert _roles(conn, newer) == ["USER"]
        finally:
            trans.rollback()
            conn.close()

    def test_rerun_is_a_no_op(self, migrations) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            signup = _insert_user(conn, creation_type="default", roles=("MODERATOR",))
            _run_upgrades(migrations, conn)
            _run_upgrades(migrations, conn)

            assert _roles(conn, signup) == ["USER"]
        finally:
            trans.rollback()
            conn.close()
