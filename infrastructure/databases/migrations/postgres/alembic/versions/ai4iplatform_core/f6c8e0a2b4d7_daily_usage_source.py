"""daily_usage.source and usage_backfill: rows backfilled from Prometheus

usage_events only has data from the day its writer shipped. The days before
it are backfilled into daily_usage from Prometheus by
scripts/usage-backfill, as estimates: request counts and units from Prometheus'
daily increases, cost at the services' current prices. source tells the two
apart:

  rollup    written by daily_usage_consolidation from usage_events (default)
  backfill  written by scripts/usage-backfill from Prometheus

source joins the dimension key (uq_daily_usage_dimensions), so the day
usage_events starts on can hold both: backfill rows for the part of the day
before its first row, rollup rows for the rest. Each writer upserts and
deletes only its own rows.

usage_backfill holds the one span the backfill covers: from first_day (IST
midnight) up to until, the instant usage_events takes over (mid-day, on the
day it starts). The Usage Dashboard reads it to know which figures are
estimates; written by every load, a single row.

Revision ID: f6c8e0a2b4d7
Revises: e2b4d6f8a0c3
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6c8e0a2b4d7"
down_revision: Union[str, None] = "e2b4d6f8a0c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "daily_usage"
COVERAGE = "usage_backfill"
DIMENSION_KEY = "uq_daily_usage_dimensions"
DIMENSIONS = (
    "usage_date", "tenant_id", "application_id", "api_key_id",
    "tier_id", "service_id", "inference_type_id", "billing_month",
)


def _dimension_key(columns: tuple[str, ...]) -> None:
    # NULLS NOT DISTINCT has no SQLAlchemy 2.0.23 option (see 4c6e8a0b2d3f).
    op.execute(f"DROP INDEX IF EXISTS {DIMENSION_KEY}")
    op.execute(f"CREATE UNIQUE INDEX {DIMENSION_KEY} ON {TABLE} ({', '.join(columns)}) NULLS NOT DISTINCT")


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("source", sa.String(16), nullable=False, server_default="rollup"))
    op.create_check_constraint("ck_daily_usage_source", TABLE, "source IN ('rollup', 'backfill')")
    _dimension_key(DIMENSIONS + ("source",))
    op.create_table(
        COVERAGE,
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("first_day", sa.Date(), nullable=False),
        sa.Column("until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_usage_backfill_single_row"),
    )


def downgrade() -> None:
    op.drop_table(COVERAGE)
    # Backfill rows can share a dimension key with rollup rows, which the
    # narrower key would refuse; they are estimates and can be re-run.
    op.execute(f"DELETE FROM {TABLE} WHERE source = 'backfill'")
    _dimension_key(DIMENSIONS)
    op.drop_constraint("ck_daily_usage_source", TABLE, type_="check")
    op.drop_column(TABLE, "source")
