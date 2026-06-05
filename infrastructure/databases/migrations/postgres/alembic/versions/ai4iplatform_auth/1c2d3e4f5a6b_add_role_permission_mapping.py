"""add_role_permission_mapping

Revision ID: 1c2d3e4f5a6b
Revises: e746f23603f0
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1c2d3e4f5a6b'
down_revision: Union[str, None] = 'e746f23603f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT 2, 131, '{SEEDER_ID}'
            WHERE NOT EXISTS (
                SELECT 1 FROM role_permission
                WHERE role_id = 2 AND permission_id = 131
            )
        """)
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM role_permission
            WHERE role_id = 2 AND permission_id = 131
        """)
    )