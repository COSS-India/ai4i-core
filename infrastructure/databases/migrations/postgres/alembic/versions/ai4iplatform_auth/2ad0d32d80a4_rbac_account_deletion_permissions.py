"""rbac_account_deletion_permissions

Revision ID: 2ad0d32d80a4
Revises: 34cee9c07750
Create Date: 2026-06-24 14:18:39.961566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ad0d32d80a4'
down_revision: Union[str, None] = '34cee9c07750'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()

    # Revoke tenant.users.delete from ADMIN
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE role_id      = (SELECT id FROM roles       WHERE name = 'ADMIN')
          AND permission_id = (SELECT id FROM permissions WHERE name = 'tenant.users.delete')
    """))

    # Grant tenant.users.delete to USER
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r
        JOIN permissions p ON p.name = 'tenant.users.delete'
        WHERE r.name = 'USER'
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))

    # Grant tenant.users.delete to MODERATOR
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r
        JOIN permissions p ON p.name = 'tenant.users.delete'
        WHERE r.name = 'MODERATOR'
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))

    # Grant tenant.users.delete to TENANT_ADMIN
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r
        JOIN permissions p ON p.name = 'tenant.users.delete'
        WHERE r.name = 'TENANT ADMIN'
          AND NOT EXISTS (
              SELECT 1 FROM role_permission rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))


def downgrade() -> None:
    pass

