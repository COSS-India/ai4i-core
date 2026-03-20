"""Add password_salt and hash_rounds to users table.

Revision ID: 001
Revises: None
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_salt", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("hash_rounds", sa.Integer(), server_default="12", nullable=True))


def downgrade() -> None:
    op.drop_column("users", "hash_rounds")
    op.drop_column("users", "password_salt")
