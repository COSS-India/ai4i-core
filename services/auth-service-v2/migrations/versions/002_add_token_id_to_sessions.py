"""Add token_id to user_sessions table.

Revision ID: 002
Revises: 001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("token_id", sa.String(36), nullable=True))
    op.create_unique_constraint("uq_user_sessions_token_id", "user_sessions", ["token_id"])
    op.create_index("ix_user_sessions_token_id", "user_sessions", ["token_id"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_token_id", table_name="user_sessions")
    op.drop_constraint("uq_user_sessions_token_id", "user_sessions", type_="unique")
    op.drop_column("user_sessions", "token_id")
