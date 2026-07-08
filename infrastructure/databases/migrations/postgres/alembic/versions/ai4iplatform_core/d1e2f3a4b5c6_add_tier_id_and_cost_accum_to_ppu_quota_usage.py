"""add_tier_id_and_cost_accum_to_ppu_quota_usage

Adds tier_id (the tier active on the tenant when a usage row is written/updated)
and cost_accum (cumulative ₹ spend for that tenant/inference/billing_month) to
ppu_quota_usage.

Revision ID: d1e2f3a4b5c6
Revises: b3c4d5e6f7a8
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'ppu_quota_usage',
        sa.Column('tier_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        'ppu_quota_usage',
        sa.Column('cost_accum', sa.Numeric(15, 8), nullable=False, server_default='0'),
    )
    op.create_index(
        op.f('ix_ppu_quota_usage_tier_id'),
        'ppu_quota_usage',
        ['tier_id'],
    )
    op.create_foreign_key(
        'fk_ppu_quota_usage_tier_id_ppu_tiers',
        'ppu_quota_usage',
        'ppu_tiers',
        ['tier_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_ppu_quota_usage_tier_id_ppu_tiers',
        'ppu_quota_usage',
        type_='foreignkey',
    )
    op.drop_index(op.f('ix_ppu_quota_usage_tier_id'), table_name='ppu_quota_usage')
    op.drop_column('ppu_quota_usage', 'cost_accum')
    op.drop_column('ppu_quota_usage', 'tier_id')
