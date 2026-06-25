"""remove_pay_per_use_tables_and_columns

Drops all pay-per-use tables and the cost_per_unit, billing_unit_type, tier
columns that were added to mm_services.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def upgrade() -> None:
    # Drop PPU columns from mm_services
    for col in ('cost_per_unit', 'billing_unit_type', 'tier'):
        if _column_exists('mm_services', col):
            op.drop_column('mm_services', col)

    # Drop tables in FK dependency order (children before parents)
    for table in (
        'subscription_plans',   # FK → quota_configs, rate_limit_configs
        'quota_service_limits', # FK → quota_configs
        'quota_configs',
        'rate_limit_configs',
        'quota_usage',
        'usage_records',
        'wallet_balances',
        'wallet_transactions',
    ):
        if _table_exists(table):
            op.drop_table(table)


def downgrade() -> None:
    # Recreate PPU tables
    op.create_table(
        'wallet_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', sa.String(64), nullable=False, index=True),
        sa.Column('amount', sa.Numeric(20, 6), nullable=False),
        sa.Column('type', sa.String(16), nullable=False),
        sa.Column('reference_id', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_wallet_transactions_tenant_id', 'wallet_transactions', ['tenant_id'])

    op.create_table(
        'wallet_balances',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('balance', sa.Numeric(20, 6), nullable=False, server_default='0'),
        sa.Column('total_plan_cost', sa.Numeric(20, 6), nullable=False, server_default='0'),
        sa.Column('total_used', sa.Numeric(20, 6), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(8), nullable=False, server_default='INR'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_wallet_balances_tenant_id', 'wallet_balances', ['tenant_id'])

    op.create_table(
        'usage_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', sa.String(64), nullable=False, index=True),
        sa.Column('api_key_id', sa.String(64), nullable=False, index=True),
        sa.Column('service_id', sa.String(128), nullable=False, index=True),
        sa.Column('units_consumed', sa.Numeric(20, 6), nullable=False),
        sa.Column('cost', sa.Numeric(20, 6), nullable=False),
        sa.Column('rate_used', sa.Numeric(20, 8), nullable=True),
        sa.Column('tier', sa.String(32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_usage_records_tenant_id', 'usage_records', ['tenant_id'])
    op.create_index('ix_usage_records_api_key_id', 'usage_records', ['api_key_id'])
    op.create_index('ix_usage_records_service_id', 'usage_records', ['service_id'])

    op.create_table(
        'quota_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', sa.String(64), nullable=False, index=True),
        sa.Column('service_id', sa.String(128), nullable=False, index=True),
        sa.Column('period', sa.String(16), nullable=False),
        sa.Column('requests_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('units_used', sa.Numeric(20, 6), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_quota_usage_tenant_id', 'quota_usage', ['tenant_id'])
    op.create_index('ix_quota_usage_service_id', 'quota_usage', ['service_id'])

    op.create_table(
        'rate_limit_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('requests_per_hour_per_api_key', sa.Integer(), nullable=False),
        sa.Column('requests_per_hour_per_tenant', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('name', name='uq_rate_limit_configs_name'),
    )
    op.create_index('ix_rate_limit_configs_name', 'rate_limit_configs', ['name'])

    op.create_table(
        'quota_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('requests_per_hour', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('name', name='uq_quota_configs_name'),
    )
    op.create_index('ix_quota_configs_name', 'quota_configs', ['name'])

    op.create_table(
        'quota_service_limits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('quota_config_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quota_configs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('service_type', sa.String(64), nullable=False),
        sa.Column('unit_type', sa.String(64), nullable=False),
        sa.Column('limit_value', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_quota_service_limits_quota_config_id', 'quota_service_limits', ['quota_config_id'])

    op.create_table(
        'subscription_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('plan_name', sa.String(128), nullable=False),
        sa.Column('cost', sa.Numeric(12, 2), nullable=False, server_default='100.00'),
        sa.Column('tier', sa.String(20), nullable=False, index=True),
        sa.Column('quota_config_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quota_configs.id'), nullable=False),
        sa.Column('rate_limit_config_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rate_limit_configs.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('plan_name', name='uq_subscription_plans_plan_name'),
        sa.UniqueConstraint('tier', name='uq_subscription_plans_tier'),
    )
    op.create_index('ix_subscription_plans_tier', 'subscription_plans', ['tier'])

    # Restore PPU columns on mm_services
    op.add_column('mm_services', sa.Column('cost_per_unit', sa.Numeric(10, 4), nullable=True))
    op.add_column('mm_services', sa.Column('billing_unit_type', sa.String(length=32), nullable=True))
    op.add_column('mm_services', sa.Column('tier', sa.String(length=20), nullable=True))
