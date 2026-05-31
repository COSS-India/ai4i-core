"""Grant traces.read (131) to TENANT ADMIN

Applies the delta for tenant-scoped trace access to already-seeded databases
(the 2362774ac241 seed migration won't re-run on existing DBs). TENANT ADMIN
needs traces.read so it passes the gateway gate on the trace-read endpoints;
ADMIN already holds it via the 'ADMIN = every permission' grant. Visibility
breadth (all vs own tenant) is decided downstream from the X-Is-Admin header,
so no new permission is required here.

Idempotent: a NOT EXISTS guard skips the grant if it already exists, so re-runs
and fresh-seeded DBs are no-ops (role_permission has no unique constraint to rely on).

Revision ID: d7a1c3f9e2b4
Revises: fa469d0a7fbb
Create Date: 2026-05-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a1c3f9e2b4'
down_revision: Union[str, None] = 'fa469d0a7fbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    # Same role/permission grant idiom as the seed migration (2362774ac241):
    #   FROM roles r JOIN permissions p ON p.name IN (...) WHERE r.name = '...'
    # The seed can use a plain INSERT because it DELETEs role_permission first;
    # this runs against live data, so a NOT EXISTS guard keeps it re-run-safe
    # (role_permission has no unique constraint on (role_id, permission_id)).
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN ('traces.read')
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
          AND permission_id = (SELECT id FROM permissions WHERE name = 'traces.read')
    """))
