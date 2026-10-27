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
    def test_self_registered_privileged_roles_are_preserved(self, migrations) -> None:
        # Change request: a self-registered user holding ADMIN, MODERATOR,
        # TENANT ADMIN or USAGE VIEWER keeps every role it has — nothing is
        # removed and USER is not added. The first version stripped these
        # and would have locked real admins out in production.
        conn = _live_connection()
        trans = conn.begin()
        try:
            usage_viewer_signup = _insert_user(conn, creation_type="default", roles=("USAGE VIEWER",))
            google_moderator = _insert_user(conn, creation_type="google", creds_at=None, roles=("USER", "MODERATOR"))
            institution_admin_signup = _insert_user(conn, creation_type="default", roles=("TENANT ADMIN",))
            admin_signup = _insert_user(conn, creation_type="default", roles=("USER", "ADMIN"))
            # A preserved role keeps the whole account untouched, GUEST included.
            guest_and_moderator = _insert_user(conn, creation_type="default", roles=("GUEST", "MODERATOR"))
            inactive_admin_signup = _insert_user(
                conn, creation_type="default", roles=("USER", "ADMIN"), is_active=False
            )
            deleted_moderator_signup = _insert_user(conn, creation_type="default", roles=("MODERATOR",), is_delete=True)

            _run_upgrades(migrations, conn)

            assert _roles(conn, usage_viewer_signup) == ["USAGE VIEWER"]
            assert _roles(conn, google_moderator) == ["MODERATOR", "USER"]
            assert _roles(conn, institution_admin_signup) == ["TENANT ADMIN"]
            assert _roles(conn, admin_signup) == ["ADMIN", "USER"]
            assert _roles(conn, guest_and_moderator) == ["GUEST", "MODERATOR"]
            assert _roles(conn, inactive_admin_signup) == ["ADMIN", "USER"]
            assert _roles(conn, deleted_moderator_signup) == ["MODERATOR"]
        finally:
            trans.rollback()
            conn.close()

    def test_other_self_registered_users_are_reset_to_user(self, migrations) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            guest_signup = _insert_user(conn, creation_type="default", roles=("GUEST",))
            google_guest = _insert_user(conn, creation_type="google", creds_at=None, roles=("USER", "GUEST"))
            roleless_signup = _insert_user(conn, creation_type="default")
            deleted_guest_signup = _insert_user(conn, creation_type="default", roles=("GUEST",), is_delete=True)
            plain_signup = _insert_user(conn, creation_type="default", roles=("USER",))
            tenant_moderator = _insert_user(
                conn, creation_type="tenant", creds_at=T_LATER, roles=("USER", "MODERATOR")
            )
            # Admin-created but stored as 'default' (2026-04-29 → 05-22):
            # the backfill must re-label it before the reset runs.
            legacy_tenant_guest = _insert_user(
                conn, creation_type="default", creds_at=T_LATER, roles=("GUEST",)
            )

            _run_upgrades(migrations, conn)

            assert _roles(conn, guest_signup) == ["USER"]
            assert _roles(conn, google_guest) == ["USER"]
            assert _roles(conn, roleless_signup) == ["USER"]
            assert _roles(conn, deleted_guest_signup) == []
            assert _roles(conn, plain_signup) == ["USER"]
            assert _roles(conn, tenant_moderator) == ["MODERATOR", "USER"]
            assert _roles(conn, legacy_tenant_guest) == ["GUEST"]
        finally:
            trans.rollback()
            conn.close()

    def test_every_self_registered_admin_keeps_admin(self, migrations) -> None:
        # Adversarial case for the old last-admin guard: when every admin is
        # self-registered, it kept ADMIN on the oldest one only. All of them
        # must keep it now.
        conn = _live_connection()
        trans = conn.begin()
        try:
            conn.execute(text(
                "DELETE FROM user_role WHERE role_id = (SELECT id FROM roles WHERE name = 'ADMIN')"
            ))
            older = _insert_user(
                conn, creation_type="default", roles=("USER", "ADMIN", "MODERATOR"),
                created_at="2026-05-01 00:00:00+00", creds_at="2026-05-01 00:00:00+00",
            )
            newer = _insert_user(
                conn, creation_type="default", roles=("ADMIN",),
                created_at="2026-06-01 00:00:00+00", creds_at="2026-06-01 00:00:00+00",
            )

            _run_upgrades(migrations, conn)

            assert _roles(conn, older) == ["ADMIN", "MODERATOR", "USER"]
            assert _roles(conn, newer) == ["ADMIN"]
        finally:
            trans.rollback()
            conn.close()

    def test_null_creation_type_user_keeps_its_roles(self, migrations) -> None:
        # Review case: a NULL creation_type isn't a known signup type, and
        # one whose credentials share its created_at (e.g. a script that
        # inserted both in one transaction) is not re-labelled by the
        # backfill either — the reset must leave it alone, not strip it.
        conn = _live_connection()
        trans = conn.begin()
        try:
            unlabelled_guest = _insert_user(conn, creation_type=None, roles=("GUEST",))

            _run_upgrades(migrations, conn)

            assert _roles(conn, unlabelled_guest) == ["GUEST"]
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

    def test_rerun_is_a_no_op(self, migrations) -> None:
        conn = _live_connection()
        trans = conn.begin()
        try:
            guest_signup = _insert_user(conn, creation_type="default", roles=("GUEST",))
            moderator_signup = _insert_user(conn, creation_type="default", roles=("MODERATOR",))
            _run_upgrades(migrations, conn)
            _run_upgrades(migrations, conn)

            assert _roles(conn, guest_signup) == ["USER"]
            assert _roles(conn, moderator_signup) == ["MODERATOR"]
        finally:
            trans.rollback()
            conn.close()

    def test_preserved_roles_exist_in_roles_table(self, migrations) -> None:
        # A typo (e.g. "TENANT_ADMIN") would preserve nothing and silently
        # strip that role again.
        _, reset = migrations
        conn = _live_connection()
        try:
            names = {row[0] for row in conn.execute(text("SELECT name FROM roles"))}
            assert set(reset.PRESERVED_ROLES) <= names
        finally:
            conn.close()
