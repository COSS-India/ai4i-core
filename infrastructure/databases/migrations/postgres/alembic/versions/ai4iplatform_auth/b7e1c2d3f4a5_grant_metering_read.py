"""Add metering.read (133) and grant it to ADMIN, MODERATOR, TENANT_ADMIN

The metering dashboard reads consumption data through three gateway-registered
GET endpoints (see auth-service/api_permissions.json):
  GET /api/v1/metering/overview
  GET /api/v1/metering/tenant-consumption
  GET /api/v1/metering/service-consumption
all gated on metering.read (133) at the gateway. platform-core then decides
breadth from the X-Permission-IDS header (role 1/2 platform-wide; role 5 own
tenant only), mirroring telemetry traces.read (131).

metering.read is added to the seed (2362774ac241) so fresh DBs get the row plus
the ADMIN grant via its CROSS JOIN. This migration covers EXISTING DBs (which
already ran the seed without 133): it inserts the permission if absent and grants
it to ADMIN, MODERATOR and TENANT_ADMIN. Name-based, NOT EXISTS guarded,
re-run-safe (same idiom as 1c2d3e4f5a6b / d7a1c3f9e2b4).

Revision ID: b7e1c2d3f4a5
Revises: 1c2d3e4f5a6b
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7e1c2d3f4a5'
down_revision: Union[str, None] = '1c2d3e4f5a6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Ensure the permission row exists (id 133, fixed to match the seed).
    conn.execute(
        sa.text(f"""
            INSERT INTO permissions (id, name, resource, action, created_by)
            VALUES (133, 'metering.read', 'metering', 'read', '{SEEDER_ID}')
            ON CONFLICT (id) DO NOTHING
        """)
    )
    # Keep the serial sequence ahead of the explicit id we just inserted.
    conn.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
        " GREATEST((SELECT MAX(id) FROM permissions), 133))"
    ))

    # 2. Grant to ADMIN, MODERATOR, TENANT_ADMIN. role_permission has no unique
    #    constraint on (role_id, permission_id), so guard with NOT EXISTS rather
    #    than ON CONFLICT.
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name = 'metering.read'
            WHERE r.name IN ('ADMIN', 'MODERATOR', 'TENANT_ADMIN')
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
          AND role_id IN (SELECT id FROM roles WHERE name IN ('ADMIN', 'MODERATOR', 'TENANT_ADMIN'))
    """))
    conn.execute(sa.text("DELETE FROM permissions WHERE name = 'metering.read'"))
