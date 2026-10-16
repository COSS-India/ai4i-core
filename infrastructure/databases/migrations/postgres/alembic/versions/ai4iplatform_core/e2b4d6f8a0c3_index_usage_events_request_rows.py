"""partial index on usage_events request rows

Revision ID: e2b4d6f8a0c3
Revises: d3f5a7c9e1b4
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2b4d6f8a0c3"
down_revision: Union[str, None] = "d3f5a7c9e1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "ix_usage_events_request_rows"
# Request rows: one per API-key request, written from its request span, with
# a status and no units (usage rows from ai-inference spans carry no status).
# Lets the Usage Dashboard find when request rows begin without a scan.
REQUEST_ROWS = "status_code IS NOT NULL AND total_units = 0"


def upgrade() -> None:
    op.create_index(INDEX, "usage_events", ["occurred_at"], postgresql_where=sa.text(REQUEST_ROWS))


def downgrade() -> None:
    op.drop_index(INDEX, table_name="usage_events")
