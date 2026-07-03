"""add_pay_per_use_columns_to_mm_services

Adds cost_per_unit, billing_unit_type, and tier columns to mm_services
for the pay-per-use billing feature.

Revision ID: a1b2c3d4e5f6
Revises: d7b2c4e6f8a1
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd7b2c4e6f8a1'
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


def upgrade() -> None:
    if not _column_exists('mm_services', 'cost_per_unit'):
        op.add_column('mm_services', sa.Column('cost_per_unit', sa.Numeric(10, 4), nullable=True))
    if not _column_exists('mm_services', 'billing_unit_type'):
        op.add_column('mm_services', sa.Column('billing_unit_type', sa.String(length=32), nullable=True))
    if not _column_exists('mm_services', 'tier'):
        op.add_column('mm_services', sa.Column('tier', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('mm_services', 'tier')
    op.drop_column('mm_services', 'billing_unit_type')
    op.drop_column('mm_services', 'cost_per_unit')
