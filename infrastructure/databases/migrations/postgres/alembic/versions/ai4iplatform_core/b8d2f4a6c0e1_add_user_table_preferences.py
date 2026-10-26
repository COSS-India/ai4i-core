"""add user_table_preferences

Per-user, per-view column selection for table views (Service List today; the
view_key keeps it reusable for other tables). One row per (user_id, view_key).

Revision ID: b8d2f4a6c0e1
Revises: e2f4a6c8b0d3
Create Date: 2026-10-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8d2f4a6c0e1"
down_revision: Union[str, None] = "e2f4a6c8b0d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "user_table_preferences"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("view_key", sa.String(64), nullable=False),
        sa.Column("visible_columns", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "view_key", name="uq_user_table_preferences_user_view"),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
