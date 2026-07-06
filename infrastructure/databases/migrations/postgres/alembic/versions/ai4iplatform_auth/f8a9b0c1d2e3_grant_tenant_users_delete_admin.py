"""Re-grant tenant.users.delete to ADMIN role

Migration 2ad0d32d80a4 revoked tenant.users.delete from ADMIN while enabling
self-deletion for USER/MODERATOR/TENANT ADMIN. Platform admins (Default Admin)
must still soft-delete tenant users from Tenant Management; the auth-service
handler already allows ADMIN via enforce_scope, but the gateway forward-auth
layer requires permission 47 unless the caller holds the admin sentinel (id 1).

This migration restores the explicit DB grant so ADMIN permission sets stay
consistent with tenant-management operations. Idempotent via NOT EXISTS.

Revision ID: f8a9b0c1d2e3
Revises: 74d5ab55e71e
Create Date: 2026-07-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "74d5ab55e71e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, :seeder_id
        FROM roles r
        JOIN permissions p ON p.name = 'tenant.users.delete'
        WHERE r.name = 'ADMIN'
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """),
        {"seeder_id": SEEDER_ID},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE role_id      = (SELECT id FROM roles       WHERE name = 'ADMIN')
          AND permission_id = (SELECT id FROM permissions WHERE name = 'tenant.users.delete')
    """))
