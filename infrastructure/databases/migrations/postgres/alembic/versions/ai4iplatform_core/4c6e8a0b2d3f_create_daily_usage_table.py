"""create daily_usage table, partitioned by month

Daily rollup of usage_events: one row per UTC day and dimension combination
(tenant, application, API key, tier, service, inference type, billing month).
usage_date is the UTC day of usage_events.occurred_at, and billing_month its
UTC month, so both match the PPU consumer's billing_month. Names (tenant,
application, tier, service, model) and the tenant's budget are copied in by
the rollup, so dashboard reads need no cross-database joins.

tenant_id, application_id and api_key_id refer to rows in the auth DB, so
they have no foreign key constraint. service_id references
mm_services.service_id, which is unique and kept when a service is
soft-deleted; tier_id and inference_type_id reference their tables too.

cost is generated from the three category costs, so it always equals their
(stored, rounded) sum. The rollup writes the three parts, never cost.

The dimension key treats NULLs as equal (NULLS NOT DISTINCT, Postgres 15+),
so the rollup can upsert rows whose application or API key is unknown.

Partitioning: range-partitioned on usage_date, one partition per calendar
month, named daily_usage_YYYY_MM, plus daily_usage_default for rows outside
every month partition. This migration creates the partitions for the UTC
month it runs in and the next one. Later months must be created before they
start by the scheduled partition job, which ships with the first writer of
this table; a month whose rows already landed in daily_usage_default cannot
get its partition until those rows are moved out. Writers always use
daily_usage itself.

usage_date, not created_at, is the partition key: Postgres requires the
partition column in every unique key, and the rollup upserts on the dimension
key. usage_date is part of that key and never changes for a row, so re-running
a day's rollup updates its rows instead of inserting duplicates. For the same
reason the primary key is (id, usage_date).

Revision ID: 4c6e8a0b2d3f
Revises: 3b5d7f9a1c2e
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4c6e8a0b2d3f"
down_revision: Union[str, None] = "3b5d7f9a1c2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "daily_usage"
DIMENSION_KEY = "uq_daily_usage_dimensions"
DIMENSIONS = (
    "usage_date", "tenant_id", "application_id", "api_key_id",
    "tier_id", "service_id", "inference_type_id", "billing_month",
)

# Months created by this migration: the current UTC month and the next.
MONTHS_AHEAD = 1

UNITS = sa.Numeric()
MONEY = sa.Numeric(18, 6)


def _zero(name: str, type_) -> sa.Column:
    return sa.Column(name, type_, nullable=False, server_default="0")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("tenant_name", sa.String(255), nullable=True),
        sa.Column("allocated_budget", sa.Numeric(15, 2), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("application_name", sa.String(255), nullable=True),
        sa.Column("api_key_id", sa.Integer(), nullable=True),
        sa.Column("tier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tier_name", sa.String(255), nullable=True),
        sa.Column("service_id", sa.String(255), nullable=True),
        sa.Column("service_name", sa.String(255), nullable=True),
        sa.Column("model_name", sa.String(255), nullable=True),
        sa.Column("inference_type_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=True),
        sa.Column("unit", sa.String(64), nullable=True),
        sa.Column("billing_month", sa.CHAR(7), nullable=False),
        _zero("request_count", sa.BigInteger()),
        _zero("success_count", sa.BigInteger()),
        _zero("failed_count", sa.BigInteger()),
        _zero("total_units", UNITS),
        _zero("cached_input_units", UNITS),
        _zero("output_units", UNITS),
        _zero("input_units_cost", MONEY),
        _zero("cached_input_units_cost", MONEY),
        _zero("output_units_cost", MONEY),
        # Generated, not checked: each cost is rounded to MONEY's scale when
        # stored, so a CHECK against an unrounded total rejects valid rows.
        sa.Column(
            "cost", MONEY, sa.Computed(
                "input_units_cost + cached_input_units_cost + output_units_cost", persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # Set by the rollup on every upsert; the default only covers the first insert.
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", "usage_date", name="pk_daily_usage"),
        sa.ForeignKeyConstraint(
            ["tier_id"], ["tiers.id"], name="fk_daily_usage_tier_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["mm_services.service_id"], name="fk_daily_usage_service_id",
        ),
        sa.ForeignKeyConstraint(
            ["inference_type_id"], ["inference_types.id"], name="fk_daily_usage_inference_type_id",
        ),
        sa.CheckConstraint("billing_month ~ '^[0-9]{4}-[0-9]{2}$'", name="ck_daily_usage_billing_month"),
        sa.CheckConstraint(
            "success_count + failed_count = request_count", name="ck_daily_usage_request_counts",
        ),
        postgresql_partition_by="RANGE (usage_date)",
    )
    # NULLS NOT DISTINCT has no SQLAlchemy 2.0.23 constraint option, so the
    # unique dimension key is created in SQL.
    op.execute(
        f"CREATE UNIQUE INDEX {DIMENSION_KEY} ON {TABLE} ({', '.join(DIMENSIONS)}) NULLS NOT DISTINCT"
    )
    op.create_index("ix_daily_usage_tenant_date", TABLE, ["tenant_id", "usage_date"])
    op.create_index("ix_daily_usage_application_date", TABLE, ["application_id", "usage_date"])
    op.create_index("ix_daily_usage_service_date", TABLE, ["service_id", "usage_date"])
    op.create_index("ix_daily_usage_billing_month", TABLE, ["billing_month", "tenant_id"])

    # Indexes and the unique key above are created on every partition,
    # including ones the partition job adds later. Month bounds are computed
    # when the migration runs (also in --sql output); usage_date is already a
    # UTC day, so they are plain dates.
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
                    to_char(month_start, 'YYYY-MM-DD'),
                    to_char(month_start + interval '1 month', 'YYYY-MM-DD')
                );
            END LOOP;
        END $$
        """
    )
    op.execute(f"CREATE TABLE {TABLE}_default PARTITION OF {TABLE} DEFAULT")


def downgrade() -> None:
    # Dropping the parent drops every partition and its indexes.
    op.drop_table(TABLE)
