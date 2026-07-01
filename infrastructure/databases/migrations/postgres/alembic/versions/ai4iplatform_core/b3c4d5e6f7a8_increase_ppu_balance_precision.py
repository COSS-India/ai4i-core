"""increase_ppu_balance_precision

Widens ppu_tenant_tier_assignments.budget_limit and available_balance from
NUMERIC(15, 4) to NUMERIC(15, 8) so that sub-cent unit rates (e.g. ₹0.000002/token)
are stored without rounding to zero.

Revision ID: b3c4d5e6f7a8
Revises: c9b397ba24f6
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'c9b397ba24f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'ppu_tenant_tier_assignments',
        'budget_limit',
        existing_type=sa.Numeric(15, 4),
        type_=sa.Numeric(15, 8),
        existing_nullable=False,
    )
    op.alter_column(
        'ppu_tenant_tier_assignments',
        'available_balance',
        existing_type=sa.Numeric(15, 4),
        type_=sa.Numeric(15, 8),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'ppu_tenant_tier_assignments',
        'available_balance',
        existing_type=sa.Numeric(15, 8),
        type_=sa.Numeric(15, 4),
        existing_nullable=False,
    )
    op.alter_column(
        'ppu_tenant_tier_assignments',
        'budget_limit',
        existing_type=sa.Numeric(15, 8),
        type_=sa.Numeric(15, 4),
        existing_nullable=False,
    )
