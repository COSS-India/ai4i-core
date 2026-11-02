"""add api_key_revoked_at to api_key

Revision ID: 0e66329b21ae
Revises: 67b0a18b2572
Create Date: 2026-10-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0e66329b21ae"
down_revision: Union[str, None] = "67b0a18b2572"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_key", sa.Column("api_key_revoked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("api_key", "api_key_revoked_at")
