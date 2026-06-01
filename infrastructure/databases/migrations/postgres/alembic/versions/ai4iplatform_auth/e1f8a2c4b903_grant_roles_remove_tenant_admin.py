"""Grant roles.remove (22) to TENANT ADMIN

Applies the delta for role-removal access to already-seeded databases
(the 2362774ac241 seed migration won't re-run on existing DBs). TENANT ADMIN
needs roles.remove so it passes the gateway gate on POST /auth/roles/remove;
ADMIN already holds it via the 'ADMIN = every permission' grant.

Without this grant the gateway forward-auth check returns INSUFFICIENT_PERMISSIONS
for all TENANT ADMIN role-removal requests, regardless of which role is being removed
or whether the target user is in the same tenant.

Idempotent: a NOT EXISTS guard skips the grant if it already exists, so re-runs
and fresh-seeded DBs are no-ops (role_permission has no unique constraint to rely on).

Revision ID: e1f8a2c4b903
Revises: d7a1c3f9e2b4
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f8a2c4b903'
down_revision: Union[str, None] = 'd7a1c3f9e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN ('roles.remove')
            WHERE r.name = 'TENANT ADMIN'
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """)
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE role_id = (SELECT id FROM roles WHERE name = 'TENANT ADMIN')
          AND permission_id = (SELECT id FROM permissions WHERE name = 'roles.remove')
    """))
