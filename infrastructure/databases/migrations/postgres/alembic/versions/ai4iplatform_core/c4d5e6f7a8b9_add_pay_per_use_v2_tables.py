"""add_pay_per_use_v2_tables

Creates the new pay-per-use v2 schema:
  - ppu_tiers            – named quota tiers
  - ppu_tier_quotas      – per-inference monthly quota per tier
  - ppu_tenant_tier_assignments – links a tenant to a tier with a budget
  - ppu_quota_usage      – rolling monthly usage counters per tenant/inference

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-06-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    return result.fetchone() is not None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :table"
        ),
        {"table": table},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if not _column_exists('mm_services', 'billing_unit_type'):
        op.add_column('mm_services', sa.Column('billing_unit_type', sa.String(32), nullable=True))
    if not _column_exists('mm_services', 'cost_per_unit'):
        op.add_column('mm_services', sa.Column('cost_per_unit', sa.Numeric(15, 8), nullable=True))
    if not _column_exists('mm_services', 'unit_size'):
        op.add_column('mm_services', sa.Column('unit_size', sa.BigInteger(), nullable=True))
    if not _column_exists('mm_services', 'unit_rate'):
        op.add_column('mm_services', sa.Column('unit_rate', sa.Numeric(15, 8), nullable=True))

    if not _table_exists('ppu_tiers'):
        op.create_table(
            'ppu_tiers',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('updated_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.UniqueConstraint('name', name='uq_ppu_tiers_name'),
        )

    if not _table_exists('ppu_tier_quotas'):
        op.create_table(
            'ppu_tier_quotas',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                'tier_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('ppu_tiers.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('inference_name', sa.String(64), nullable=False),
            sa.Column('monthly_quota', sa.BigInteger(), nullable=False),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('updated_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.UniqueConstraint('tier_id', 'inference_name', name='uq_ppu_tier_quotas_tier_inference'),
        )
        op.create_index('ix_ppu_tier_quotas_tier_id', 'ppu_tier_quotas', ['tier_id'])

    if not _table_exists('ppu_tenant_tier_assignments'):
        op.create_table(
            'ppu_tenant_tier_assignments',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column(
                'tier_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('ppu_tiers.id'),
                nullable=False,
            ),
            sa.Column('budget_limit', sa.Numeric(15, 4), nullable=False),
            sa.Column('available_balance', sa.Numeric(15, 4), nullable=False),
            sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
            sa.Column('effective_to', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('updated_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        )
        op.create_index('ix_ppu_tenant_tier_assignments_tenant_id', 'ppu_tenant_tier_assignments', ['tenant_id'])
        op.create_index('ix_ppu_tenant_tier_assignments_tier_id', 'ppu_tenant_tier_assignments', ['tier_id'])

    if not _table_exists('ppu_quota_usage'):
        op.create_table(
            'ppu_quota_usage',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('inference_name', sa.String(64), nullable=False),
            sa.Column('billing_month', sa.String(7), nullable=False),
            sa.Column('monthly_quota_snap', sa.BigInteger(), nullable=True),
            sa.Column('units_used', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('updated_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.UniqueConstraint(
                'tenant_id',
                'inference_name',
                'billing_month',
                name='uq_ppu_quota_usage_tenant_inference_month',
            ),
        )
        op.create_index('ix_ppu_quota_usage_tenant_id', 'ppu_quota_usage', ['tenant_id'])
        op.create_index('ix_ppu_quota_usage_inference_name', 'ppu_quota_usage', ['inference_name'])


def downgrade() -> None:
    op.drop_column('mm_services', 'unit_rate')
    op.drop_column('mm_services', 'unit_size')
    op.drop_column('mm_services', 'cost_per_unit')
    op.drop_column('mm_services', 'billing_unit_type')

    op.drop_index('ix_ppu_quota_usage_inference_name', table_name='ppu_quota_usage')
    op.drop_index('ix_ppu_quota_usage_tenant_id', table_name='ppu_quota_usage')
    op.drop_table('ppu_quota_usage')

    op.drop_index('ix_ppu_tenant_tier_assignments_tier_id', table_name='ppu_tenant_tier_assignments')
    op.drop_index('ix_ppu_tenant_tier_assignments_tenant_id', table_name='ppu_tenant_tier_assignments')
    op.drop_table('ppu_tenant_tier_assignments')

    op.drop_index('ix_ppu_tier_quotas_tier_id', table_name='ppu_tier_quotas')
    op.drop_table('ppu_tier_quotas')

    op.drop_table('ppu_tiers')
