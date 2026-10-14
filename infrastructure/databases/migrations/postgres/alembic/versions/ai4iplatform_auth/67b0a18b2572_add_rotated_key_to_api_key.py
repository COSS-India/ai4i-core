"""add rotated_key and rotated_key_expires_at to api_key

Revision ID: 67b0a18b2572
Revises: 51379ee0d696
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "67b0a18b2572"
down_revision: Union[str, None] = "51379ee0d696"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_key", sa.Column("rotated_key", sa.String(32), nullable=True))
    op.add_column("api_key", sa.Column("rotated_key_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "uq_api_key_rotated_key",
        "api_key",
        ["rotated_key"],
        unique=True,
        postgresql_where=sa.text("rotated_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_api_key_rotated_key", table_name="api_key")
    op.drop_column("api_key", "rotated_key_expires_at")
    op.drop_column("api_key", "rotated_key")
