"""Grant configs.read (120) to all roles.

Revision ID: e8b9c0d1e2f3
Revises: ba0818f032cd
Create Date: 2026-11-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8b9c0d1e2f3"
down_revision: Union[str, None] = "ba0818f032cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"
PERMISSION_NAME = "configs.read"

# ADMIN and MODERATOR already have this — only the missing roles are listed.
GRANTED_ROLES = ("USER", "GUEST", "TENANT ADMIN", "USAGE VIEWER")


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, :seeder_id
            FROM roles r
            JOIN permissions p ON p.name = :name
            WHERE r.name = ANY(:roles)
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """),
        {"name": PERMISSION_NAME, "roles": list(GRANTED_ROLES), "seeder_id": SEEDER_ID},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM role_permission
            WHERE permission_id = (SELECT id FROM permissions WHERE name = :name)
              AND role_id IN (SELECT id FROM roles WHERE name = ANY(:roles))
        """),
        {"name": PERMISSION_NAME, "roles": list(GRANTED_ROLES)},
    )
