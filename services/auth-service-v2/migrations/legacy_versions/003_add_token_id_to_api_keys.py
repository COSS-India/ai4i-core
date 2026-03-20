"""Add token_id and status to api_keys table.

Revision ID: 003
Revises: 002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("token_id", sa.String(36), nullable=True))
    op.add_column("api_keys", sa.Column("status", sa.String(20), server_default="active", nullable=True))
    op.create_unique_constraint("uq_api_keys_token_id", "api_keys", ["token_id"])
    op.create_index("ix_api_keys_token_id", "api_keys", ["token_id"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_token_id", table_name="api_keys")
    op.drop_constraint("uq_api_keys_token_id", "api_keys", type_="unique")
    op.drop_column("api_keys", "status")
    op.drop_column("api_keys", "token_id")
