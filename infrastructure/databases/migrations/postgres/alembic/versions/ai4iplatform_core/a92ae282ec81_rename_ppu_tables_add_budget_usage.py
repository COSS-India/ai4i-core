"""rename_ppu_tables_add_budget_usage

Renames ppu_tiers, ppu_tier_quotas, ppu_quota_usage to drop the ppu_ prefix.
Renames units_used to monthly_quota_used on quota_usage.
Creates budget_usage table.

Revision ID: a92ae282ec81
Revises: f7e8d9c0b1a2
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a92ae282ec81'
down_revision: Union[str, None] = '1edf17b191a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename ppu_tiers → tiers (rename constraint too)
    op.rename_table('ppu_tiers', 'tiers')
    op.execute('ALTER TABLE tiers RENAME CONSTRAINT uq_ppu_tiers_name TO uq_tiers_name')

    # 2. Rename ppu_tier_quotas → tier_quotas
    op.rename_table('ppu_tier_quotas', 'tier_quotas')
    op.execute(
        'ALTER TABLE tier_quotas RENAME CONSTRAINT '
        'uq_ppu_tier_quotas_tier_inference TO uq_tier_quotas_tier_inference'
    )
    op.execute('ALTER INDEX ix_ppu_tier_quotas_tier_id RENAME TO ix_tier_quotas_tier_id')

    # 3. Rename ppu_quota_usage → quota_usage
    op.rename_table('ppu_quota_usage', 'quota_usage')
    op.execute(
        'ALTER TABLE quota_usage RENAME CONSTRAINT '
        'uq_ppu_quota_usage_tenant_inference_month_tier TO uq_quota_usage_tenant_inference_month_tier'
    )
    op.execute('ALTER INDEX ix_ppu_quota_usage_tenant_id RENAME TO ix_quota_usage_tenant_id')
    op.execute('ALTER INDEX ix_ppu_quota_usage_inference_name RENAME TO ix_quota_usage_inference_name')
    op.execute('ALTER INDEX ix_ppu_quota_usage_billing_month_tenant RENAME TO ix_quota_usage_billing_month_tenant')
    op.execute('ALTER INDEX ix_ppu_quota_usage_tier_id RENAME TO ix_quota_usage_tier_id')
    op.execute(
        'ALTER TABLE quota_usage RENAME CONSTRAINT '
        'fk_ppu_quota_usage_tier_id_ppu_tiers TO fk_quota_usage_tier_id_tiers'
    )

    # 4. Rename units_used → monthly_quota_used
    op.alter_column('quota_usage', 'units_used', new_column_name='monthly_quota_used')

    # 5. Create budget_usage table
    op.create_table(
        'budget_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('api_key_id', sa.Integer(), nullable=False),
        sa.Column('api_key_budget_snap', sa.Numeric(15, 8), nullable=True),
        sa.Column('api_key_budget_used', sa.Numeric(15, 8), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('api_key_id', name='uq_budget_usage_api_key_id'),
    )


def downgrade() -> None:
    # Drop budget_usage
    op.drop_constraint('uq_budget_usage_api_key_id', 'budget_usage', type_='unique')
    op.drop_table('budget_usage')

    # Rename monthly_quota_used → units_used
    op.alter_column('quota_usage', 'monthly_quota_used', new_column_name='units_used')

    # Restore quota_usage → ppu_quota_usage
    op.execute(
        'ALTER TABLE quota_usage RENAME CONSTRAINT '
        'fk_quota_usage_tier_id_tiers TO fk_ppu_quota_usage_tier_id_ppu_tiers'
    )
    op.execute('ALTER INDEX ix_quota_usage_tier_id RENAME TO ix_ppu_quota_usage_tier_id')
    op.execute('ALTER INDEX ix_quota_usage_billing_month_tenant RENAME TO ix_ppu_quota_usage_billing_month_tenant')
    op.execute('ALTER INDEX ix_quota_usage_inference_name RENAME TO ix_ppu_quota_usage_inference_name')
    op.execute('ALTER INDEX ix_quota_usage_tenant_id RENAME TO ix_ppu_quota_usage_tenant_id')
    op.execute(
        'ALTER TABLE quota_usage RENAME CONSTRAINT '
        'uq_quota_usage_tenant_inference_month_tier TO uq_ppu_quota_usage_tenant_inference_month_tier'
    )
    op.rename_table('quota_usage', 'ppu_quota_usage')

    # Restore tier_quotas → ppu_tier_quotas
    op.execute('ALTER INDEX ix_tier_quotas_tier_id RENAME TO ix_ppu_tier_quotas_tier_id')
    op.execute(
        'ALTER TABLE tier_quotas RENAME CONSTRAINT '
        'uq_tier_quotas_tier_inference TO uq_ppu_tier_quotas_tier_inference'
    )
    op.rename_table('tier_quotas', 'ppu_tier_quotas')

    # Restore tiers → ppu_tiers
    op.execute('ALTER TABLE tiers RENAME CONSTRAINT uq_tiers_name TO uq_ppu_tiers_name')
    op.rename_table('tiers', 'ppu_tiers')
