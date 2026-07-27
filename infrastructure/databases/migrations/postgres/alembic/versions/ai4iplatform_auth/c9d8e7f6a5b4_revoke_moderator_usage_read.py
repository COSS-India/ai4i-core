"""Revoke MODERATOR access to usage.read (134) / usage.tenant_read (135)

Moderators should no longer see the PPU usage dashboard endpoints
(usage-summary, usage-tenants, usage-tenant). ADMIN keeps platform-wide
access; TENANT ADMIN keeps usage.tenant_read scoped to its own tenant
(enforced in platform-core via X-Tenant-Id).

Revision ID: c9d8e7f6a5b4
Revises: d5e6f7a8b9c0
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9d8e7f6a5b4'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE name IN ('usage.read', 'usage.tenant_read')
        )
          AND role_id IN (SELECT id FROM roles WHERE name = 'MODERATOR')
    """))


def downgrade() -> None:
    conn = op.get_bind()
    SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"
    conn.execute(
        sa.text("""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, :seeder_id
            FROM roles r
            JOIN permissions p ON p.name IN ('usage.read', 'usage.tenant_read')
            WHERE r.name = 'MODERATOR'
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """),
        {"seeder_id": SEEDER_ID},
    )
