"""add applications.service_fallbacks

Revision ID: 7a28dca07e9d
Revises: a7c3e9f15b28
Create Date: 2026-10-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "7a28dca07e9d"
down_revision: Union[str, None] = "a7c3e9f15b28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


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
