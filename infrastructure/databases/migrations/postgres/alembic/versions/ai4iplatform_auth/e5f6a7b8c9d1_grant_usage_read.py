"""Add usage.read (134) and grant it to ADMIN, MODERATOR, TENANT_ADMIN

The PPU usage dashboard reads consumption data through three gateway-registered
GET endpoints (see auth-service/api_permissions.json):
  GET /api/v1/usage/summary   — platform-wide aggregate (admin/moderator only, enforced in route)
  GET /api/v1/usage/tenants   — all-tenant list (admin/moderator only, enforced in route)
  GET /api/v1/usage/tenant    — single-tenant detail (admin/moderator platform-wide; role 5 own tenant only)
all gated on usage.read (134) at the gateway. platform-core then decides
breadth from the X-Permission-IDS header, mirroring metering.read (133).

Revision ID: e5f6a7b8c9d1
Revises: ad79a2cfe40f
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d1'
down_revision: Union[str, None] = 'ad79a2cfe40f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Ensure the permission row exists (id 134).
    conn.execute(
        sa.text(f"""
            INSERT INTO permissions (id, name, resource, action, created_by)
            VALUES (134, 'usage.read', 'usage', 'read', '{SEEDER_ID}')
            ON CONFLICT (id) DO NOTHING
        """)
    )
    conn.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
        " GREATEST((SELECT MAX(id) FROM permissions), 134))"
    ))

    # 2. Grant to ADMIN, MODERATOR, TENANT_ADMIN.
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name = 'usage.read'
            WHERE r.name IN ('ADMIN', 'MODERATOR', 'TENANT ADMIN')
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
        WHERE permission_id = (SELECT id FROM permissions WHERE name = 'usage.read')
          AND role_id IN (SELECT id FROM roles WHERE name IN ('ADMIN', 'MODERATOR', 'TENANT ADMIN'))
    """))
    conn.execute(sa.text("DELETE FROM permissions WHERE name = 'usage.read'"))
