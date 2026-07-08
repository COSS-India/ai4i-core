"""Fix metering.read (133) grant for the TENANT ADMIN role (name mismatch)

The earlier grant migration (b7e1c2d3f4a5) granted metering.read to roles named
'ADMIN', 'MODERATOR' and 'TENANT_ADMIN'. But the seed (2362774ac241) names the
tenant-admin role 'TENANT ADMIN' — with a SPACE, not an underscore (see also the
traces.read grant d7a1c3f9e2b4, which correctly uses 'TENANT ADMIN'). As a
result the name-based WHERE never matched the tenant-admin role, so metering.read
was never granted to it. Tenant admins therefore got a gateway 403
(INSUFFICIENT_PERMISSIONS) on GET /api/v1/metering/* and could not see their own
tenant-scoped consumption.

b7e1c2d3f4a5 is already applied, so it must not be edited (never edit an applied
migration). This follow-up grants metering.read to the correctly-named
'TENANT ADMIN' role. Name-based, NOT EXISTS guarded, re-run-safe.

Revision ID: d3e4f5a6b7c8
Revises: c1d2e3f4a5b6
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()

    # Grant metering.read to the tenant-admin role, addressed by its ACTUAL
    # seeded name 'TENANT ADMIN' (space). role_permission has no unique
    # constraint on (role_id, permission_id), so guard with NOT EXISTS.
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name = 'metering.read'
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
        WHERE permission_id = (SELECT id FROM permissions WHERE name = 'metering.read')
          AND role_id IN (SELECT id FROM roles WHERE name = 'TENANT ADMIN')
    """))
