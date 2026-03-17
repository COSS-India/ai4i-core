"""initial_alerting_schema (37a8d2ea829f) — no-op for revision compatibility

Revision ID: 37a8d2ea829f
Revises: 
Create Date: 2026-03-09 16:11:54

Environments that already ran the old 37a8d2ea829f have this revision in alembic_version.
This file is a no-op so Alembic can locate the revision. The correct schema is applied
in b4d3d8ecd4f1 (the next migration).
"""
from typing import Sequence, Union

revision: str = '37a8d2ea829f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op: correct schema is in b4d3d8ecd4f1
    pass


def downgrade() -> None:
    pass
