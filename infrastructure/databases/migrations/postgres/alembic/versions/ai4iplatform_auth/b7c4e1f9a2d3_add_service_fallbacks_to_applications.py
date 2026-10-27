"""add service_fallbacks to applications

Map of requested service_id -> ordered list of fallback service_ids, set per
Application. Existing rows default to {} (no fallback), so behaviour is
unchanged until an Application is configured.

Revision ID: b7c4e1f9a2d3
Revises: a7c3e9f15b28
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b7c4e1f9a2d3"
down_revision: Union[str, None] = "a7c3e9f15b28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "service_fallbacks",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("applications", "service_fallbacks")
