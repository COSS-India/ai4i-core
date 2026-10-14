"""merge usage_events merge and PII flatten heads

Pure merge, no DDL: b8d0f2a4c6e9 (merge) and f4a7c2e9d1b3 (PII policy type
flatten) both revise a7c3e9f1b5d2 and c2e4a6f8b0d1.

Revision ID: d3f5a7c9e1b4
Revises: b8d0f2a4c6e9, f4a7c2e9d1b3
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'd3f5a7c9e1b4'
down_revision: Union[str, Sequence[str], None] = ('b8d0f2a4c6e9', 'f4a7c2e9d1b3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
