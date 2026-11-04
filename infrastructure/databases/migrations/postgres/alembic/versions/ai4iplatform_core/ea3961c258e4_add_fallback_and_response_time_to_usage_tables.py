"""add fallback and response time columns to usage_events and daily_usage

usage_events: both describe a request and are written on request rows
(status set, no units) from the request span; usage rows leave them at their
defaults.

- served_by_fallback (boolean, default false): the service the client asked
  for was unavailable and the request was sent to a fallback service,
  whether a fallback answered it (service_id is then that fallback) or every
  fallback failed (service_id stays the requested service).
- response_time_ms (integer): the request span's duration (end - start) in
  milliseconds. NULL on usage rows.

daily_usage: the daily rollup of those columns, per dimension row, counted
from request rows the same way as request_count.

- fallback_count: requests sent to a fallback service. Already part of
  request_count; never more than it.
- total_response_time_ms: the sum of response_time_ms. The average response
  time is total_response_time_ms / request_count; both are additive, so any
  period or set of rows averages by summing them.
- server_error_count: platform-side failures, requests whose status is 500
  or above (server errors, and timeouts, which reach the client as 502/503).
  Part of failed_count, which also counts the client's 4xx errors; the error
  rate is server_error_count / request_count.

Percentiles (P95) are not additive across days or dimension rows, so they are
not stored in daily_usage; they are read from usage_events.response_time_ms,
which keeps every day.

Added on the partitioned parents, so Postgres adds each column to every
attached partition, the DEFAULT one included, and to every partition created
later. Constant defaults and nullable columns only touch the catalog, not the
rows.

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

DAILY_USAGE_COLUMNS = ("fallback_count", "total_response_time_ms", "server_error_count")


def upgrade() -> None:
    op.add_column(
        "usage_events",
        sa.Column("served_by_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("usage_events", sa.Column("response_time_ms", sa.Integer(), nullable=True))

    for name in DAILY_USAGE_COLUMNS:
        op.add_column("daily_usage", sa.Column(name, sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    for name in reversed(DAILY_USAGE_COLUMNS):
        op.drop_column("daily_usage", name)

    op.drop_column("usage_events", "response_time_ms")
    op.drop_column("usage_events", "served_by_fallback")
