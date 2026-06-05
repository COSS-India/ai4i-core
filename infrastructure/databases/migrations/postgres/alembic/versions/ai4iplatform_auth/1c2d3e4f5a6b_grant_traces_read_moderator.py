"""Grant traces.read (131) to MODERATOR

The Logs Dashboard reads traces through GET /telemetry/traces/search and
GET /telemetry/traces/{trace_id}, both gated on traces.read (131) at the
gateway. MODERATOR never held it (the seed grants metrics/alerts/dashboards
but not traces), so moderators were rejected before reaching the service.
Downstream breadth (all tenants for moderator) is decided from the
X-Permission-IDS header by platform-core.

Same name-based grant idiom as d7a1c3f9e2b4 (TENANT ADMIN): resolve role and
permission by name — role ids are serial-assigned by the seed, so hard-coded
numeric ids are not portable across environments.

Revision ID: 1c2d3e4f5a6b
Revises: f6a7b8c9d0e1
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1c2d3e4f5a6b'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    # NOT EXISTS guard keeps this re-run-safe (role_permission has no unique
    # constraint on (role_id, permission_id), so ON CONFLICT would throw).
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN ('traces.read')
            WHERE r.name = 'MODERATOR'
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
        WHERE role_id = (SELECT id FROM roles WHERE name = 'MODERATOR')
          AND permission_id = (SELECT id FROM permissions WHERE name = 'traces.read')
    """))
