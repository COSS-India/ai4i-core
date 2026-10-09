"""create usage_events table, partitioned by month

One row per billed request (API-key traffic), keyed by its correlation id.
Holds the request's units and cost split by category: input, cached input
and output. For LLM requests the split is real; for other task types the
whole charge is in input_units_cost and the cached/output columns are 0.

tenant_id, application_id and api_key_id refer to rows in the auth DB, and
service_id to mm_services.service_id (not unique: services are soft-deleted),
so none of them has a foreign key constraint.

Partitioning: range-partitioned on created_at, one partition per IST calendar
month, named usage_events_YYYY_MM. This migration creates the parent table and
the October 2026 partition only. Later partitions are created, and old ones
dropped, by a scheduled job outside alembic. Writers always insert into
usage_events itself; Postgres routes each row to its month's partition.

Postgres requires the partition column in every unique key, so the primary
key is (correlation_id, created_at): a correlation id is only unique within a
row's created_at, not across the whole table.

Revision ID: 3b5d7f9a1c2e
Revises: 7a3c9e1f5b2d
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3b5d7f9a1c2e"
down_revision: Union[str, None] = "7a3c9e1f5b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "usage_events"

UNITS = sa.Numeric()
MONEY = sa.Numeric(18, 6)

# Month boundaries are IST midnight, written with an explicit offset so they
# don't depend on the session's TimeZone setting.
IST_OFFSET = "+05:30"
FIRST_PARTITION = "usage_events_2026_10"
FIRST_PARTITION_FROM = f"2026-10-01 00:00:00{IST_OFFSET}"
FIRST_PARTITION_TO = f"2026-11-01 00:00:00{IST_OFFSET}"


def _zero(name: str, type_) -> sa.Column:
    return sa.Column(name, type_, nullable=False, server_default="0")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("api_key_id", sa.Integer(), nullable=True),
        sa.Column("tier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service_id", sa.String(255), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=True),
        sa.Column("unit_of_measurement", sa.String(64), nullable=True),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        _zero("total_units", UNITS),
        _zero("cached_input_units", UNITS),
        _zero("output_units", UNITS),
        _zero("input_units_cost", MONEY),
        _zero("cached_input_units_cost", MONEY),
        _zero("output_units_cost", MONEY),
        _zero("total_cost", MONEY),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("correlation_id", "created_at", name="pk_usage_events"),
        sa.CheckConstraint(
            "total_cost = input_units_cost + cached_input_units_cost + output_units_cost",
            name="ck_usage_events_total_cost",
        ),
        sa.CheckConstraint(
            "cached_input_units >= 0 AND output_units >= 0 AND cached_input_units + output_units <= total_units",
            name="ck_usage_events_units",
        ),
        postgresql_partition_by="RANGE (created_at)",
    )
    # Indexes on the parent are created on every partition, including ones
    # the scheduled job adds later with CREATE TABLE ... PARTITION OF.
    op.create_index("ix_usage_events_tenant_created", TABLE, ["tenant_id", "created_at"])
    op.create_index("ix_usage_events_api_key_created", TABLE, ["api_key_id", "created_at"])
    op.create_index("ix_usage_events_service_created", TABLE, ["service_id", "created_at"])

    op.execute(
        f"CREATE TABLE {FIRST_PARTITION} PARTITION OF {TABLE} "
        f"FOR VALUES FROM ('{FIRST_PARTITION_FROM}') TO ('{FIRST_PARTITION_TO}')"
    )


def downgrade() -> None:
    # Dropping the parent drops every partition, including ones the
    # scheduled job created, and their indexes.
    op.drop_table(TABLE)
