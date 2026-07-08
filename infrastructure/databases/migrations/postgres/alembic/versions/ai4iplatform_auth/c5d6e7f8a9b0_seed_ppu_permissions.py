"""Seed PPU tier and tenant-assignment permissions (140–144) and grant to ADMIN only.

Pay-Per-Use endpoints registered in auth-service/api_permissions.json:
  GET    /api/v1/pay-per-use/tiers       → permissionRequired: 140 (ppu.tier.read)
  GET    /api/v1/pay-per-use/tier        → permissionRequired: 140 (ppu.tier.read)
  POST   /api/v1/pay-per-use/tier        → permissionRequired: 141 (ppu.tier.create)
  PATCH  /api/v1/pay-per-use/tier        → permissionRequired: 142 (ppu.tier.update)
  DELETE /api/v1/pay-per-use/tier        → permissionRequired: 143 (ppu.tier.delete)
  POST   /api/v1/pay-per-use/tenant/tier → permissionRequired: 144 (ppu.tenant.assign)

All PPU operations are admin-only (no grant to MODERATOR or TENANT_ADMIN).
Inserts are ON CONFLICT DO NOTHING / NOT EXISTS guarded — re-run-safe.

Revision ID: c5d6e7f8a9b0
Revises: 2ad0d32d80a4
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = '2ad0d32d80a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

PPU_PERMISSIONS = [
    (140, "ppu.tier.read",     "ppu.tier",   "read"),
    (141, "ppu.tier.create",   "ppu.tier",   "create"),
    (142, "ppu.tier.update",   "ppu.tier",   "update"),
    (143, "ppu.tier.delete",   "ppu.tier",   "delete"),
    (144, "ppu.tenant.assign", "ppu.tenant", "assign"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Ensure permission rows exist (explicit IDs to match api_permissions.json).
    for pid, name, resource, action in PPU_PERMISSIONS:
        conn.execute(
            sa.text(f"""
                INSERT INTO permissions (id, name, resource, action, created_by)
                VALUES ({pid}, '{name}', '{resource}', '{action}', '{SEEDER_ID}')
                ON CONFLICT (id) DO NOTHING
            """)
        )

    # Keep the serial sequence ahead of the highest explicit id we inserted.
    conn.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
        " GREATEST((SELECT MAX(id) FROM permissions), 144))"
    ))

    # 2. Grant all PPU permissions to ADMIN only.
    for _, name, _, _ in PPU_PERMISSIONS:
        conn.execute(
            sa.text(f"""
                INSERT INTO role_permission (role_id, permission_id, created_by)
                SELECT r.id, p.id, '{SEEDER_ID}'
                FROM roles r
                JOIN permissions p ON p.name = '{name}'
                WHERE r.name = 'ADMIN'
                  AND NOT EXISTS (
                      SELECT 1 FROM role_permission rp
                      WHERE rp.role_id = r.id AND rp.permission_id = p.id
                  )
            """)
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Remove ADMIN grants for all PPU permissions.
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE permission_id IN (
            SELECT id FROM permissions
            WHERE name IN (
                'ppu.tier.read', 'ppu.tier.create', 'ppu.tier.update',
                'ppu.tier.delete', 'ppu.tenant.assign'
            )
        )
          AND role_id = (SELECT id FROM roles WHERE name = 'ADMIN')
    """))

    # Remove the permission rows themselves.
    conn.execute(sa.text("""
        DELETE FROM permissions
        WHERE name IN (
            'ppu.tier.read', 'ppu.tier.create', 'ppu.tier.update',
            'ppu.tier.delete', 'ppu.tenant.assign'
        )
    """))
