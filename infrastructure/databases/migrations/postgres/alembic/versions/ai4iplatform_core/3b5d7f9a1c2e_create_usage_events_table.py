"""create usage_events table, partitioned by month

One row per billed span (API-key traffic). A request normally has one; a TTS
per_item request has one per chunk, all with the same correlation id. Holds
the span's units and cost split by category: input, cached input and output.
For LLM requests the split is real; for other task types the whole charge is
in input_units_cost and the cached/output columns are 0. total_cost is
generated from the three, so it always equals their (stored, rounded) sum.

tenant_id, application_id and api_key_id refer to rows in the auth DB, so
they have no foreign key constraint. service_id references
mm_services.service_id, which is unique and kept when a service is
soft-deleted; tier_id and inference_type_id reference their tables too.

Times are UTC. occurred_at is the span's end time, the same instant the PPU
consumer derives billing_month from, so a row's partition month and its
billing month always agree. created_at is only when the row was inserted.

Partitioning: range-partitioned on occurred_at, one partition per UTC
calendar month, named usage_events_YYYY_MM, plus usage_events_default for
rows outside every month partition. This migration creates the partitions for
the month it runs in and the next one. Later months must be created before
they start by the scheduled partition job, which ships with the first writer
of this table; a month whose rows already landed in usage_events_default
cannot get its partition until those rows are moved out. Writers always
insert into usage_events itself; Postgres routes each row to its partition.

The primary key is (correlation_id, span_id, occurred_at). Postgres requires
the partition column in every unique key; occurred_at comes from the span, so
a Kafka redelivery of the same span hits the key instead of adding a row.

Revision ID: 3b5d7f9a1c2e
Revises: f4a8c2d6e1b7
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3b5d7f9a1c2e"
down_revision: Union[str, None] = "f4a8c2d6e1b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "usage_events"
# Months created by this migration: the current UTC month and the next.
MONTHS_AHEAD = 1

UNITS = sa.Numeric()
MONEY = sa.Numeric(18, 6)


def _zero(name: str, type_) -> sa.Column:
    return sa.Column(name, type_, nullable=False, server_default="0")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("span_id", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("api_key_id", sa.Integer(), nullable=True),
        sa.Column("tier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service_id", sa.String(255), nullable=True),
        sa.Column("inference_type_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=True),
        sa.Column("unit_of_measurement", sa.String(64), nullable=True),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        _zero("total_units", UNITS),
        _zero("cached_input_units", UNITS),
        _zero("output_units", UNITS),
        _zero("input_units_cost", MONEY),
        _zero("cached_input_units_cost", MONEY),
        _zero("output_units_cost", MONEY),
        # Generated, not checked: each cost is rounded to MONEY's scale when
        # stored, so a CHECK against an unrounded total rejects valid rows.
        sa.Column(
            "total_cost", MONEY, sa.Computed(
                "input_units_cost + cached_input_units_cost + output_units_cost", persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("correlation_id", "span_id", "occurred_at", name="pk_usage_events"),
        sa.ForeignKeyConstraint(
            ["tier_id"], ["tiers.id"], name="fk_usage_events_tier_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["mm_services.service_id"], name="fk_usage_events_service_id",
        ),
        sa.ForeignKeyConstraint(
            ["inference_type_id"], ["inference_types.id"], name="fk_usage_events_inference_type_id",
        ),
        sa.CheckConstraint(
            "cached_input_units >= 0 AND output_units >= 0 AND cached_input_units + output_units <= total_units",
            name="ck_usage_events_units",
        ),
        postgresql_partition_by="RANGE (occurred_at)",
    )
    # Indexes on the parent are created on every partition, including ones
    # the partition job adds later with CREATE TABLE ... PARTITION OF.
    op.create_index("ix_usage_events_tenant_occurred", TABLE, ["tenant_id", "occurred_at"])
    op.create_index("ix_usage_events_api_key_occurred", TABLE, ["api_key_id", "occurred_at"])
    op.create_index("ix_usage_events_service_occurred", TABLE, ["service_id", "occurred_at"])

    # Month bounds are computed when the migration runs (also in --sql
    # output) and written with an explicit +00 offset, so they don't depend
    # on the session's TimeZone setting.
    op.execute(
        f"""
        DO $$
        DECLARE
            first_month date := date_trunc('month', now() AT TIME ZONE 'UTC')::date;
            month_start date;
        BEGIN
            FOR i IN 0..{MONTHS_AHEAD} LOOP
                month_start := (first_month + make_interval(months => i))::date;
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF {TABLE} FOR VALUES FROM (%L) TO (%L)',
                    '{TABLE}_' || to_char(month_start, 'YYYY_MM'),
                    to_char(month_start, 'YYYY-MM-DD') || ' 00:00:00+00',
                    to_char(month_start + interval '1 month', 'YYYY-MM-DD') || ' 00:00:00+00'
                );
            END LOOP;
        END $$
        """
    )
    op.execute(f"CREATE TABLE {TABLE}_default PARTITION OF {TABLE} DEFAULT")


def downgrade() -> None:
    # Dropping the parent drops every partition, including ones the
    # partition job created, and their indexes.
    op.drop_table(TABLE)
