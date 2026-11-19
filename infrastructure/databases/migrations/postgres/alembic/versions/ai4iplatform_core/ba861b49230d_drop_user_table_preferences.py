"""drop user_table_preferences

Added in b8d2f4a6c0e1 for the Service List column picker's per-user
preferences (GET/PUT/DELETE /preferences/columns/{view_key}). That endpoint
and the GET /services/columns catalogue endpoint were never called by the
frontend — column visibility is stored client-side instead — so both routes
and this table's backing code have been removed.

Revision ID: ba861b49230d
Revises: 602fce4c3c41
Create Date: 2026-11-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ba861b49230d"
down_revision: Union[str, None] = "602fce4c3c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "user_table_preferences"


def upgrade() -> None:
    op.drop_table(TABLE)


def downgrade() -> None:
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
