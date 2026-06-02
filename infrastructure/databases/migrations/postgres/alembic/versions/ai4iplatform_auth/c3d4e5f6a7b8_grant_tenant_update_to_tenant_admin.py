"""Grant tenant.update permission to TENANT ADMIN role

TENANT ADMIN must be able to update their own tenant's profile fields via
PATCH /api/v1/tenants/{tenant_id}. Both the profile and status endpoints share
permission 42 (tenant.update) at the gateway level; the status endpoint is
protected from Tenant Admin by an ADMIN-only check in update_tenant_status.

The seed migration (2362774ac241) is updated in parallel so fresh installs are correct.
This migration fixes already-seeded databases.

Related: AI4IDS-1750

Idempotent: INSERT ... WHERE NOT EXISTS is a no-op if the row already exists.

Revision ID: c3d4e5f6a7b8
Revises: f5a8c2d6e9b1
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'f5a8c2d6e9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, :seeder_id
        FROM roles r
        JOIN permissions p ON p.name = 'tenant.update'
        WHERE r.name = 'TENANT ADMIN'
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """), {"seeder_id": SEEDER_ID})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE role_id      = (SELECT id FROM roles       WHERE name = 'TENANT ADMIN')
          AND permission_id = (SELECT id FROM permissions WHERE name = 'tenant.update')
    """))
