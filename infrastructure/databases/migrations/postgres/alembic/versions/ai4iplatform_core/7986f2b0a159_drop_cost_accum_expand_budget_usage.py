"""drop_cost_accum_from_quota_usage

Drops the cost_accum column from quota_usage. Cost tracking moves to
budget_usage.api_key_budget_used, keyed by api_key_id.

Revision ID: 7986f2b0a159
Revises: c3d4e5f6a7b8
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '7986f2b0a159'
down_revision: Union[str, None] = 'a92ae282ec81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('quota_usage', 'cost_accum')


def downgrade() -> None:
    op.add_column(
        'quota_usage',
        sa.Column('cost_accum', sa.Numeric(15, 8), nullable=False, server_default='0'),
    )
