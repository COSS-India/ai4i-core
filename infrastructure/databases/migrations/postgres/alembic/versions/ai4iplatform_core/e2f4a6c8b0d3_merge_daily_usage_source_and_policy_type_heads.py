"""merge daily_usage source and policy type unique constraint heads

Pure merge, no DDL: a1c3e5f7b9d2 (daily_usage.source) and a1b3c5d7e9f2 (drop
the policy type name unique constraint) both branch off a9d4f2b6c8e1 and touch
unrelated tables.

Revision ID: e2f4a6c8b0d3
Revises: a1c3e5f7b9d2, a1b3c5d7e9f2
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'e2f4a6c8b0d3'
down_revision: Union[str, Sequence[str], None] = ('a1c3e5f7b9d2', 'a1b3c5d7e9f2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
