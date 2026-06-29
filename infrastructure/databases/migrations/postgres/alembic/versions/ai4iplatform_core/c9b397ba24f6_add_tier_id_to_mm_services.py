"""add_tier_id_to_mm_services

Adds a nullable tier_id foreign key on mm_services referencing ppu_tiers.id.
A service may optionally belong to a PPU tier; deleting the tier sets this field to NULL.

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
        sa.Column('tier_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_mm_services_tier_id',
        'mm_services',
        'ppu_tiers',
        ['tier_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_mm_services_tier_id', 'mm_services', ['tier_id'])


def downgrade() -> None:
    op.drop_index('ix_mm_services_tier_id', table_name='mm_services')
    op.drop_constraint('fk_mm_services_tier_id', 'mm_services', type_='foreignkey')
    op.drop_column('mm_services', 'tier_id')
