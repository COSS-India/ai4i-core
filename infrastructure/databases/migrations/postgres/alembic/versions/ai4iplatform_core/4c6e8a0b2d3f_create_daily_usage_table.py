"""create daily_usage table

Daily rollup of usage_events: one row per IST day and dimension combination
(tenant, application, API key, tier, service, task type, billing month).
Names (tenant, application, tier, service, model) and the tenant's budget are
copied in by the rollup, so dashboard reads need no cross-database joins.

tenant_id, application_id and api_key_id refer to rows in the auth DB, and
service_id to mm_services.service_id (not unique: services are soft-deleted),
so those have no foreign key constraint. tier_id and inference_type_id do.

The dimension key treats NULLs as equal (NULLS NOT DISTINCT, Postgres 15+),
so the rollup can upsert rows whose application or API key is unknown.

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

UNITS = sa.Numeric()
MONEY = sa.Numeric(18, 6)


def _zero(name: str, type_) -> sa.Column:
    return sa.Column(name, type_, nullable=False, server_default="0")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
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
        _zero("cost", MONEY),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # Set by the rollup on every upsert; the default only covers the first insert.
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tier_id"], ["tiers.id"], name="fk_daily_usage_tier_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["inference_type_id"], ["inference_types.id"], name="fk_daily_usage_inference_type_id",
        ),
        sa.CheckConstraint("billing_month ~ '^[0-9]{4}-[0-9]{2}$'", name="ck_daily_usage_billing_month"),
        sa.CheckConstraint(
            "success_count + failed_count = request_count", name="ck_daily_usage_request_counts",
        ),
        sa.CheckConstraint(
            "cost = input_units_cost + cached_input_units_cost + output_units_cost", name="ck_daily_usage_cost",
        ),
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


def downgrade() -> None:
    op.drop_index("ix_daily_usage_billing_month", table_name=TABLE)
    op.drop_index("ix_daily_usage_service_date", table_name=TABLE)
    op.drop_index("ix_daily_usage_application_date", table_name=TABLE)
    op.drop_index("ix_daily_usage_tenant_date", table_name=TABLE)
    op.execute(f"DROP INDEX IF EXISTS {DIMENSION_KEY}")
    op.drop_table(TABLE)
