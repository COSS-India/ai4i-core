"""remove_feature_flags_20260430

Revision ID: a3f1e2d4b8c9
Revises: 5c424da577cc
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1e2d4b8c9'
down_revision: Union[str, None] = '5c424da577cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('feature_flag_evaluations')
    op.drop_table('feature_flags')


def downgrade() -> None:
    op.create_table('feature_flags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_enabled', sa.Boolean(), nullable=True),
    sa.Column('rollout_percentage', sa.String(length=255), nullable=True),
    sa.Column('target_users', sa.JSON(), nullable=True),
    sa.Column('environment', sa.String(length=50), nullable=False),
    sa.Column('unleash_flag_name', sa.String(length=255), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evaluation_count', sa.Integer(), nullable=True),
    sa.Column('last_evaluated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'environment', name='uq_feature_flags_name_environment')
    )
    op.create_table('feature_flag_evaluations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('flag_name', sa.String(length=255), nullable=False),
    sa.Column('user_id', sa.String(length=255), nullable=True),
    sa.Column('context', sa.JSON(), nullable=True),
    sa.Column('result', sa.Boolean(), nullable=True),
    sa.Column('variant', sa.String(length=100), nullable=True),
    sa.Column('evaluated_value', sa.JSON(), nullable=True),
    sa.Column('environment', sa.String(length=50), nullable=False),
    sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evaluation_reason', sa.String(length=50), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
