"""add policy_id_seq sequence for atomic PID generation

Revision ID: d1e3f5a7b9c2
Revises: b3f1a9e2c7d5
Create Date: 2026-10-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d1e3f5a7b9c2"
down_revision: Union[str, None] = "b3f1a9e2c7d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS policy_id_seq")
    # Advance the sequence past any existing IDs so nextval() never collides.
    # is_called=false means nextval() will return exactly this value next call.
    op.execute(
        """
        SELECT setval(
            'policy_id_seq',
            COALESCE(
                (SELECT MAX(CAST(SUBSTRING(policy_id FROM 5) AS INTEGER))
                 FROM policy
                 WHERE policy_id ~ '^PID-[0-9]+$'),
                0
            ) + 1,
            false
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS policy_id_seq")
