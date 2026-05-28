"""drop_smr_tenant_policies

Revision ID: a1b2c3d4e5f6
Revises: 31d7bc3f4379
Create Date: 2026-05-27 14:43:54.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '31d7bc3f4379'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('smr_tenant_policies')


def downgrade() -> None:
    op.create_table(
        'smr_tenant_policies',
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('latency_policy', sa.String(length=20), server_default='medium', nullable=False),
        sa.Column('cost_policy', sa.String(length=20), server_default='tier_2', nullable=False),
        sa.Column('accuracy_policy', sa.String(length=20), server_default='standard', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('tenant_id'),
    )
