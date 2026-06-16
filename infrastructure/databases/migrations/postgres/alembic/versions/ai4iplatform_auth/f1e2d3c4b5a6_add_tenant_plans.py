"""add_tenant_plans

Revision ID: f1e2d3c4b5a6
Revises: 9d2d9eb83297
Create Date: 2026-05-27 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f1e2d3c4b5a6'
down_revision: Union[str, None] = '9d2d9eb83297'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tenant_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('plan_name', sa.String(length=128), nullable=False),
        sa.Column('tier', sa.String(length=32), nullable=False),
        sa.Column('plan_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('quota_config', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('rate_limit_config', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('allowed_services', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tenant_plans_tenant_id'), 'tenant_plans', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_tenant_plans_plan_id'), 'tenant_plans', ['plan_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tenant_plans_plan_id'), table_name='tenant_plans')
    op.drop_index(op.f('ix_tenant_plans_tenant_id'), table_name='tenant_plans')
    op.drop_table('tenant_plans')
