"""add rotated_at to api_key

Revision ID: 74435be97765
Revises: 0e66329b21ae
Create Date: 2026-10-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "74435be97765"
down_revision: Union[str, None] = "0e66329b21ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_key", sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("api_key", "rotated_at")
