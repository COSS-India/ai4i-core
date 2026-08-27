"""Grant DML on applications to the app's runtime DB role.

The applications table (migration e9f0a1b2c3d4) inherited no privileges for
AUTH_DB_USER: unlike the original tables, there is no ALTER DEFAULT
PRIVILEGES rule in this project granting new tables to that role
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
from typing import Sequence, Union

from alembic import op

revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = 'a170c093332e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    role = os.getenv("AUTH_DB_USER")
    if not role:
        # No role configured (e.g. a superuser-only local setup) — nothing to grant.
        return
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON applications TO "{role}"')
    # The identity column's sequence is a separate grantable object in Postgres —
    # table DML privileges alone don't cover it, and INSERT (nextval on it)
    # fails with InsufficientPrivilegeError without this.
    op.execute(f'GRANT USAGE, SELECT ON SEQUENCE applications_id_seq TO "{role}"')


def downgrade() -> None:
    role = os.getenv("AUTH_DB_USER")
    if not role:
        return
    op.execute(f'REVOKE USAGE, SELECT ON SEQUENCE applications_id_seq FROM "{role}"')
    op.execute(f'REVOKE SELECT, INSERT, UPDATE, DELETE ON applications FROM "{role}"')
