"""create usage_events table

One row per billed request (API-key traffic), keyed by its correlation id.
Holds the request's units and cost split by category: input, cached input
and output. For LLM requests the split is real; for other task types the
whole charge is in input_units_cost and the cached/output columns are 0.

tenant_id, application_id and api_key_id refer to rows in the auth DB, and
service_id to mm_services.service_id (not unique: services are soft-deleted),
so none of them has a foreign key constraint.

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


def _zero(name: str, type_) -> sa.Column:
    return sa.Column(name, type_, nullable=False, server_default="0")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("correlation_id", sa.String(64), primary_key=True),
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
        sa.CheckConstraint(
            "total_cost = input_units_cost + cached_input_units_cost + output_units_cost",
            name="ck_usage_events_total_cost",
        ),
        sa.CheckConstraint(
            "cached_input_units >= 0 AND output_units >= 0 AND cached_input_units + output_units <= total_units",
            name="ck_usage_events_units",
        ),
    )
    op.create_index("ix_usage_events_tenant_created", TABLE, ["tenant_id", "created_at"])
    op.create_index("ix_usage_events_api_key_created", TABLE, ["api_key_id", "created_at"])
    op.create_index("ix_usage_events_service_created", TABLE, ["service_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_service_created", table_name=TABLE)
    op.drop_index("ix_usage_events_api_key_created", table_name=TABLE)
    op.drop_index("ix_usage_events_tenant_created", table_name=TABLE)
    op.drop_table(TABLE)
