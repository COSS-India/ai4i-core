"""Grant tenant.read, ppu.tier.read, users.profile.update to PROGRAM ADMIN.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

MIGRATION_ID = "5eed0001-0000-0000-0000-000000000000"
ROLE_NAME = "PROGRAM ADMIN"

GRANT_PERMISSION_NAMES = [
    "tenant.read",
    "ppu.tier.read",
    "users.profile.update",
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{MIGRATION_ID}'
            FROM roles r
            JOIN permissions p ON p.name = ANY(:names)
            WHERE r.name = :role_name
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """),
        {"names": GRANT_PERMISSION_NAMES, "role_name": ROLE_NAME},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM role_permission
            WHERE role_id = (SELECT id FROM roles WHERE name = :role_name)
              AND permission_id IN (SELECT id FROM permissions WHERE name = ANY(:names))
        """),
        {"role_name": ROLE_NAME, "names": GRANT_PERMISSION_NAMES},
    )
