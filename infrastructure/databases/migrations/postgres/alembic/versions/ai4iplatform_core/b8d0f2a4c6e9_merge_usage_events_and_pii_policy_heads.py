"""merge usage_events and PII policy type heads

Pure merge, no DDL: a7c3e9f1b5d2 (usage_events) and c2e4a6f8b0d1 (PII policy
type reseed) both branch off d1e3f5a7b9c2 and touch unrelated tables.

Revision ID: b8d0f2a4c6e9
Revises: a7c3e9f1b5d2, c2e4a6f8b0d1
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'b8d0f2a4c6e9'
down_revision: Union[str, Sequence[str], None] = ('a7c3e9f1b5d2', 'c2e4a6f8b0d1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
