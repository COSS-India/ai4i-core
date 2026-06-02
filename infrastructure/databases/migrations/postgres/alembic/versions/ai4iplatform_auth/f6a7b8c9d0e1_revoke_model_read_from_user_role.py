"""Revoke model.read permission (id=55) from USER role

Revision ID: f6a7b8c9d0e1
Revises: d41e361421f6
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'd41e361421f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM role_permission
            WHERE permission_id = 55
              AND role_id = (SELECT id FROM roles WHERE name = 'USER')
        """)
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, 55, '{SEEDER_ID}'
            FROM roles r
            WHERE r.name = 'USER'
            ON CONFLICT DO NOTHING
        """)
    )
