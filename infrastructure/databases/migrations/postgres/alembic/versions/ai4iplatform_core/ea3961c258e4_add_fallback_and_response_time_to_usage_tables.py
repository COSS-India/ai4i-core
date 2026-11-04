"""add fallback and response time columns to usage_events and daily_usage

Revision ID: ea3961c258e4
Revises: 8fbe729b1331
Create Date: 2026-11-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ea3961c258e4"
down_revision: Union[str, None] = "8fbe729b1331"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DAILY_USAGE_COLUMNS = ("fallback_count", "total_response_time_ms", "response_time_count", "server_error_count")


def upgrade() -> None:
    op.add_column(
        "usage_events",
        sa.Column("sent_to_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("usage_events", sa.Column("response_time_ms", sa.Integer(), nullable=True))

    for name in DAILY_USAGE_COLUMNS:
        op.add_column("daily_usage", sa.Column(name, sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    for name in reversed(DAILY_USAGE_COLUMNS):
        op.drop_column("daily_usage", name)

    op.drop_column("usage_events", "response_time_ms")
    op.drop_column("usage_events", "sent_to_fallback")
