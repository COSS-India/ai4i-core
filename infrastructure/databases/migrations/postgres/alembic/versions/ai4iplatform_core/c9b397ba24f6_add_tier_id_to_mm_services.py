"""add_tier_ids_to_mm_services

Adds a nullable tier_ids ARRAY(String) column on mm_services.
A service may optionally belong to multiple PPU tiers.

Revision ID: c9b397ba24f6
Revises: c4d5e6f7a8b9
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c9b397ba24f6'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'mm_services',
        sa.Column('tier_ids', postgresql.ARRAY(sa.String()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('mm_services', 'tier_ids')
