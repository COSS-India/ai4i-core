"""Grant llm.inference to GUEST role

The home-page LLM card is gated on the GUEST role holding llm.inference.
GUEST previously only had asr.inference / nmt.inference / tts.inference.

Revision ID: a2b3c4d5e6f7
Revises: 790badc042e1
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = '790badc042e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, :seeder_id
            FROM roles r
            JOIN permissions p ON p.name = 'llm.inference'
            WHERE r.name = 'GUEST'
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
        WHERE role_id IN (SELECT id FROM roles WHERE name = 'GUEST')
          AND permission_id IN (SELECT id FROM permissions WHERE name = 'llm.inference')
    """))
