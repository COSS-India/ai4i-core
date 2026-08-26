"""Grant tenant.users.delete to USAGE VIEWER role.

The frontend (rbac.ts canSelfDeleteAccount) allows USER, TENANT ADMIN and
USAGE VIEWER to self-delete their account via DELETE
/api/v1/auth/tenants/{tenant_id}/users/{user_id}. Migration 2ad0d32d80a4
granted the required tenant.users.delete permission to USER, MODERATOR and
TENANT ADMIN, but USAGE VIEWER (seeded earlier as PROGRAM ADMIN in
a3b4c5d6e7f8_seed_program_admin.py) was never included, so self-deletion
returns 403 INSUFFICIENT_PERMISSIONS for that role. This migration closes
that gap.

Revision ID: d6e7f8a9b1c2
Revises: c5d6e7f8a9b1
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6e7f8a9b1c2"
down_revision: Union[str, None] = "c5d6e7f8a9b1"
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
        WHERE r.name = 'USAGE VIEWER'
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
        WHERE role_id      = (SELECT id FROM roles       WHERE name = 'USAGE VIEWER')
          AND permission_id = (SELECT id FROM permissions WHERE name = 'tenant.users.delete')
    """))
