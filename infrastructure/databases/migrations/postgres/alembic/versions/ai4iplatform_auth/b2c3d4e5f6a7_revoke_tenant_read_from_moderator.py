"""Revoke tenant.read permission from MODERATOR role

MODERATOR should not be able to read tenant details — GET /api/v1/tenants and
GET /api/v1/tenants/{tenant_id} should return 403 for Moderator.

The gateway allows MODERATOR through those endpoints via tenant.read (permission 41),
so revoking here blocks at the gateway level without requiring application-layer changes.

The seed migration (2362774ac241) is updated in parallel so fresh installs are correct.
This migration fixes already-seeded databases.

Related: AI4IDS-1748

Idempotent: DELETE WHERE is a no-op if the row is absent.

Revision ID: b2c3d4e5f6a7
Revises: e3f4a5b6c7d8
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE role_id      = (SELECT id FROM roles       WHERE name = 'MODERATOR')
          AND permission_id = (SELECT id FROM permissions WHERE name = 'tenant.read')
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, :seeder_id
        FROM roles r
        JOIN permissions p ON p.name = 'tenant.read'
        WHERE r.name = 'MODERATOR'
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """), {"seeder_id": SEEDER_ID})
