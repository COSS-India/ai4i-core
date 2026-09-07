"""Grant DML on applications to the app's runtime DB role.

The applications table (migration e9f0a1b2c3d4) inherited no privileges for
the app's runtime role: unlike the original tables, there is no ALTER
DEFAULT PRIVILEGES rule in this project granting new tables to that role
automatically, so every brand-new table needs an explicit GRANT here (this
project doesn't seed that role or run migrations as it, so the grant can't
happen at table-creation time either). Without this, every query against
applications fails with asyncpg.InsufficientPrivilegeError even though the
table and rows are otherwise fine.

Revision ID: a9b8c7d6e5f4
Revises: a170c093332e
Create Date: 2026-08-27 00:00:00.000000

"""
import os
from typing import Optional, Sequence, Union
from urllib.parse import unquote, urlsplit

from alembic import op

revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = 'a170c093332e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def _resolve_app_db_role() -> str:
    """Resolve the role auth-service actually connects as, mirroring
    AuthSettings.get_database_url()'s exact fallback chain
    (services/auth-service/app/core/config.py) — not the narrower chain
    migration_registry.py uses to pick who RUNS this migration (which can
    legitimately be a different role, e.g. a migration-runner/superuser).

    A prior version of this migration read only os.getenv("AUTH_DB_USER"):
    when the running app resolves its role through AUTH_DATABASE_URL/
    DATABASE_URL, or falls back to POSTGRES_USER, or falls all the way back
    to the literal "postgres" default, that read silently missed it — the
    grant landed on the wrong role (or wasn't attempted at all), the
    migration still stamped as applied, and every applications query then
    failed with InsufficientPrivilegeError with nothing in the migration log
    to explain why. Always returns a concrete role now (never empty),
    exactly matching what get_database_url() would actually connect as.
    """
    for url_var in ("AUTH_DATABASE_URL", "DATABASE_URL"):
        url = os.getenv(url_var)
        if url:
            username = urlsplit(url).username
            if username:
                return unquote(username)
    return os.getenv("AUTH_DB_USER") or os.getenv("POSTGRES_USER") or "postgres"


def _table_owner(table_name: str) -> Optional[str]:
    conn = op.get_bind()
    return conn.exec_driver_sql(
        "SELECT tableowner FROM pg_tables WHERE tablename = %s", (table_name,)
    ).scalar()


def upgrade() -> None:
    role = _resolve_app_db_role()
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON applications TO "{role}"')
    # The identity column's sequence is a separate grantable object in Postgres —
    # table DML privileges alone don't cover it, and INSERT (nextval on it)
    # fails with InsufficientPrivilegeError without this.
    op.execute(f'GRANT USAGE, SELECT ON SEQUENCE applications_id_seq TO "{role}"')


def downgrade() -> None:
    role = _resolve_app_db_role()
    # If the resolved role OWNS the table, it already held full DML before
    # this migration's upgrade() ever ran (ownership implies it) — that GRANT
    # was a no-op for it, so REVOKE here would strip privileges this
    # migration never granted, leaving the DB worse off than before it ran.
    if _table_owner("applications") == role:
        return
    op.execute(f'REVOKE USAGE, SELECT ON SEQUENCE applications_id_seq FROM "{role}"')
    op.execute(f'REVOKE SELECT, INSERT, UPDATE, DELETE ON applications FROM "{role}"')
