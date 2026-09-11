"""widen_numeric_columns_for_large_quotas_and_costs

Widens:
- tier_quotas.monthly_quota, pending_monthly_quota: Numeric(15,4) -> Numeric(16,4)
  to support monthly quota values up to 100 billion.
- quota_usage.monthly_quota_snap, monthly_quota_used: Numeric(15,4) -> Numeric(16,4)
  for consistency with tier_quotas.
- mm_services.cost_per_unit, unit_rate: Numeric(15,8) -> Numeric(16,8)
  to support cost per unit values up to 10 million.

Revision ID: a3f9c2b1e7d5
Revises: 6dc231d5809a
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f9c2b1e7d5'
down_revision: Union[str, None] = '6dc231d5809a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('tier_quotas', 'monthly_quota',
                    existing_nullable=False,
                    type_=sa.Numeric(16, 4))
    op.alter_column('tier_quotas', 'pending_monthly_quota',
                    existing_nullable=True,
                    type_=sa.Numeric(16, 4))
    op.alter_column('quota_usage', 'monthly_quota_snap',
                    existing_nullable=True,
                    type_=sa.Numeric(16, 4))
    op.alter_column('quota_usage', 'monthly_quota_used',
                    existing_nullable=False,
                    type_=sa.Numeric(16, 4))
    op.alter_column('mm_services', 'cost_per_unit',
                    existing_nullable=True,
                    type_=sa.Numeric(16, 8))
    op.alter_column('mm_services', 'unit_rate',
                    existing_nullable=True,
                    type_=sa.Numeric(16, 8))


def downgrade() -> None:
    op.alter_column('mm_services', 'unit_rate',
                    existing_nullable=True,
                    type_=sa.Numeric(15, 8))
    op.alter_column('mm_services', 'cost_per_unit',
                    existing_nullable=True,
                    type_=sa.Numeric(15, 8))
    op.alter_column('quota_usage', 'monthly_quota_used',
                    existing_nullable=False,
                    type_=sa.Numeric(15, 4))
    op.alter_column('quota_usage', 'monthly_quota_snap',
                    existing_nullable=True,
                    type_=sa.Numeric(15, 4))
    op.alter_column('tier_quotas', 'pending_monthly_quota',
                    existing_nullable=True,
                    type_=sa.Numeric(15, 4))
    op.alter_column('tier_quotas', 'monthly_quota',
                    existing_nullable=False,
                    type_=sa.Numeric(15, 4))
