"""remove_policy_from_mm_services

Drops the policy column from mm_services. It was accepted client-side via
PATCH /api/v1/services (latency/cost/accuracy SLA tiers) but never consumed
by any routing/business logic and was absent from the create payload, so the
field and its backing column are being removed as unused surface — any
existing value is dead data with no reader, so no backup/migration of its
contents is needed before the drop.

Revision ID: 1edf17b191a7
Revises: a7c9e1f3b5d7
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '1edf17b191a7'
down_revision: Union[str, Sequence[str], None] = 'a7c9e1f3b5d7'
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
    if _column_exists('mm_services', 'policy'):
        op.drop_column('mm_services', 'policy')


def downgrade() -> None:
    if not _column_exists('mm_services', 'policy'):
        op.add_column(
            'mm_services',
            sa.Column('policy', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
