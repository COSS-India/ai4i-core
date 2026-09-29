"""add_monitoring_alert_types_to_notification_catalog

Extends the configs_notification_alert enums for the "Define Monitoring
Alerts" ticket:

* notification_alert_type_enum  += MONITORING — a third catalog family,
  alongside NOTIFICATION and ALERT (metering). Monitoring alerts follow a
  separate configuration and recipient model from metering, so they get
  their own ``?type=`` filter on the catalog GET rather than sharing ALERT.
* notification_alert_module_enum += MONITORING
* notification_alert_name_enum   += ERROR_RATE_4XX, ERROR_RATE_5XX,
  LATENCY_P50, LATENCY_P95, LATENCY_P99

No existing row, column or table is touched — every column already
references these types with create_type=False, so extending the types is
enough.

Kept separate from the seed migration (seed_monitoring_alert_catalog) for
the same reason b83dc4f704d2 was split from 6dc231d5809a: a newly added
enum value cannot be referenced in the same transaction that adds it.

Revision ID: f1a3c5e7b9d1
Revises: c6e8f0a2b4d6
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a3c5e7b9d1'
down_revision: Union[str, None] = 'c6e8f0a2b4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NAME_ENUM = "notification_alert_name_enum"
TYPE_ENUM = "notification_alert_type_enum"
MODULE_ENUM = "notification_alert_module_enum"

# enum type -> (column it backs, values this revision adds, values it had before)
_ENUM_CHANGES = {
    NAME_ENUM: (
        "name",
        ["ERROR_RATE_4XX", "ERROR_RATE_5XX", "LATENCY_P50", "LATENCY_P95", "LATENCY_P99"],
        [
            "TIER_ASSIGNED", "TIER_CHANGED", "BUDGET_ASSIGNED", "BUDGET_UPDATED",
            "QUOTA_LIMIT_UPDATED", "QUOTA_EXHAUSTED", "BUDGET_EXHAUSTED",
            "QUOTA_THRESHOLD", "BUDGET_THRESHOLD",
        ],
    ),
    TYPE_ENUM: ("type", ["MONITORING"], ["NOTIFICATION", "ALERT"]),
    MODULE_ENUM: ("module", ["MONITORING"], ["TIER", "BUDGET", "QUOTA"]),
}


def upgrade() -> None:
    for enum_name, (_, new_values, _) in _ENUM_CHANGES.items():
        for value in new_values:
            # Guarded the same way b83dc4f704d2 adds its values: ALTER TYPE
            # ... ADD VALUE isn't idempotent on its own.
            op.execute(
                f"""
                DO $migration$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_enum e
                        JOIN pg_type t ON e.enumtypid = t.oid
                        WHERE t.typname = '{enum_name}'
                          AND e.enumlabel = '{value}'
                    ) THEN
                        ALTER TYPE {enum_name} ADD VALUE '{value}';
                    END IF;
                END $migration$;
                """
            )


def downgrade() -> None:
    # Postgres cannot drop a single enum value — rebuild each type without
    # this revision's values, same technique as b83dc4f704d2's downgrade.
    # Assumes seed_monitoring_alert_catalog's downgrade (which deletes the 5
    # MONITORING rows) has already run — the normal alembic order.
    for enum_name, (column, _, old_values) in _ENUM_CHANGES.items():
        values = ", ".join(f"'{value}'" for value in old_values)
        op.execute(
            f"""
            DO $migration$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN
                    ALTER TYPE {enum_name} RENAME TO {enum_name}_old;
                END IF;
                CREATE TYPE {enum_name} AS ENUM ({values});
                ALTER TABLE configs_notification_alert
                    ALTER COLUMN {column} TYPE {enum_name}
                    USING {column}::text::{enum_name};
                DROP TYPE IF EXISTS {enum_name}_old;
            END $migration$;
            """
        )
