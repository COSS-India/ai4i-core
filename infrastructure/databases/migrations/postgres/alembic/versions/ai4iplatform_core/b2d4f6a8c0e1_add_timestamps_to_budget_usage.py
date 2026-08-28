"""add_timestamps_to_budget_usage

Revision ID: b2d4f6a8c0e1
Revises: a1b3c5d7e9f0
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, None] = 'a1b3c5d7e9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('budget_usage', sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column('budget_usage', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))


def downgrade() -> None:
    op.drop_column('budget_usage', 'updated_at')
    op.drop_column('budget_usage', 'created_at')
