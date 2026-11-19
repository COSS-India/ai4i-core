"""add KEY_ROTATED name and API_KEY module to the notification catalog enums

Revision ID: 5611c5d7c73d
Revises: 97c3bf253272
Create Date: 2026-11-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = '5611c5d7c73d'
down_revision: Union[str, None] = '97c3bf253272'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# enum type -> (column it backs, value this revision adds, values it had before)
_ENUM_CHANGES = {
    "notification_alert_name_enum": (
        "name",
        "KEY_ROTATED",
        [
            "TIER_ASSIGNED", "TIER_CHANGED", "BUDGET_ASSIGNED", "BUDGET_UPDATED",
            "QUOTA_LIMIT_UPDATED", "QUOTA_EXHAUSTED", "BUDGET_EXHAUSTED",
            "QUOTA_THRESHOLD", "BUDGET_THRESHOLD",
            "ERROR_RATE_4XX", "ERROR_RATE_5XX", "LATENCY_P50", "LATENCY_P95", "LATENCY_P99",
        ],
    ),
    "notification_alert_module_enum": ("module", "API_KEY", ["TIER", "BUDGET", "QUOTA", "MONITORING"]),
}


def upgrade() -> None:
    for enum_name, (_, value, _) in _ENUM_CHANGES.items():
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
    # Postgres cannot drop one enum value: rebuild each type without it.
    for enum_name, (column, _, old_values) in _ENUM_CHANGES.items():
        values = ", ".join(f"'{value}'" for value in old_values)
        op.execute(
            f"""
            DO $migration$
            BEGIN
                ALTER TYPE {enum_name} RENAME TO {enum_name}_old;
                CREATE TYPE {enum_name} AS ENUM ({values});
                ALTER TABLE configs_notification_alert
                    ALTER COLUMN {column} TYPE {enum_name}
                    USING {column}::text::{enum_name};
                DROP TYPE {enum_name}_old;
            END $migration$;
            """
        )
