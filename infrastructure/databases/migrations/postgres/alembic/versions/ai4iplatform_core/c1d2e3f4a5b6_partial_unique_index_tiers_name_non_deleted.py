"""partial_unique_index_tiers_name_non_deleted

Replaces the plain unique constraint on tiers.name with a partial unique
index that excludes DELETED tiers, allowing the same name to be reused
after a tier is deleted.

Revision ID: c1d2e3f4a5b6
Revises: a3f9c2b1e7d5
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'a3f9c2b1e7d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('uq_tiers_name', 'tiers', type_='unique')
    op.create_index(
        'uq_tiers_name_active',
        'tiers',
        ['name'],
        unique=True,
        postgresql_where=sa.text("status != 'DELETED'"),
    )


def downgrade() -> None:
    op.drop_index('uq_tiers_name_active', table_name='tiers')
    op.create_unique_constraint('uq_tiers_name', 'tiers', ['name'])
