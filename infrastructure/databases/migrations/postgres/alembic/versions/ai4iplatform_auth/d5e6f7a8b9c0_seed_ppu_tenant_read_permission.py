"""Seed PPU tenant-read permission (145) and grant to ADMIN only.

Pay-Per-Use endpoint registered in auth-service/api_permissions.json:
  GET  /api/v1/pay-per-use/tenant/tier  → permissionRequired: 145 (ppu.tenant.read)

Admin-only operation — no grant to MODERATOR or TENANT_ADMIN.
Inserts are ON CONFLICT DO NOTHING / NOT EXISTS guarded — re-run-safe.

Revision ID: d5e6f7a8b9c0
Revises: f8a9b0c1d2e3
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Insert permission row (explicit ID to match api_permissions.json).
    conn.execute(sa.text(f"""
        INSERT INTO permissions (id, name, resource, action, created_by)
        VALUES (145, 'ppu.tenant.read', 'ppu.tenant', 'read', '{SEEDER_ID}')
        ON CONFLICT (id) DO NOTHING
    """))

    # Keep the serial sequence ahead of the highest explicit id we inserted.
    conn.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
        " GREATEST((SELECT MAX(id) FROM permissions), 145))"
    ))

    # 2. Grant ppu.tenant.read to ADMIN only.
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r
        JOIN permissions p ON p.name = 'ppu.tenant.read'
        WHERE r.name = 'ADMIN'
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Remove ADMIN grant for ppu.tenant.read.
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE permission_id = (SELECT id FROM permissions WHERE name = 'ppu.tenant.read')
          AND role_id = (SELECT id FROM roles WHERE name = 'ADMIN')
    """))

    # Remove the permission row.
    conn.execute(sa.text("""
        DELETE FROM permissions WHERE name = 'ppu.tenant.read'
    """))
