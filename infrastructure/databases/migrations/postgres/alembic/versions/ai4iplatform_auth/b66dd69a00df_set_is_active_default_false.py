"""Set is_active default to false for users table

Revision ID: b66dd69a00df
Revises: a55cc68a99ce
Create Date: 2026-05-12 06:16:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b66dd69a00df'
down_revision: Union[str, None] = 'a55cc68a99ce'
branch_labels: Union[str, Sequence[str]] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Add server_default=false to is_active column in users table
    # New users created via register() must remain inactive until email verification
    op.alter_column('users', 'is_active',
               existing_type=sa.Boolean(),
               server_default='false',
               existing_nullable=False)


def downgrade() -> None:
    op.alter_column('users', 'is_active',
               existing_type=sa.Boolean(),
               server_default=None,
               existing_nullable=False)
