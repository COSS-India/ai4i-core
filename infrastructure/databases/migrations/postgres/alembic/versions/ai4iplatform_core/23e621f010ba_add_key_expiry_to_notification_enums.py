"""add GRACE_PERIOD_EXPIRING / API_KEY_EXPIRING names and the DAYS threshold unit

Revision ID: 23e621f010ba
Revises: 445916bf95f9
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = '23e621f010ba'
down_revision: Union[str, None] = '445916bf95f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# enum type -> (table, column it backs, values this revision adds, values it had before)
_ENUM_CHANGES = {
    "notification_alert_name_enum": (
        "configs_notification_alert",
        "name",
        ["GRACE_PERIOD_EXPIRING", "API_KEY_EXPIRING"],
        [
            "TIER_ASSIGNED", "TIER_CHANGED", "BUDGET_ASSIGNED", "BUDGET_UPDATED",
            "QUOTA_LIMIT_UPDATED", "QUOTA_EXHAUSTED", "BUDGET_EXHAUSTED",
            "QUOTA_THRESHOLD", "BUDGET_THRESHOLD",
            "ERROR_RATE_4XX", "ERROR_RATE_5XX", "LATENCY_P50", "LATENCY_P95", "LATENCY_P99",
            "KEY_ROTATED",
        ],
    ),
    "notification_threshold_unit_enum": (
        "notification_alert_threshold",
        "unit",
        ["DAYS"],
        ["PERCENT", "SECONDS"],
    ),
}


def upgrade() -> None:
    # The new values are used only by the next revision: Postgres can't use an
    # enum value in the transaction that added it.
    for enum_name, (_, _, values, _) in _ENUM_CHANGES.items():
        for value in values:
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
    # Postgres cannot drop one enum value: rebuild each type without them.
    # The CHECK constraint on unit compares to a literal of the type, so it
    # is dropped and re-created around the rebuild.
    op.execute(
        "ALTER TABLE notification_alert_threshold "
        "DROP CONSTRAINT IF EXISTS ck_notification_alert_threshold_percent;"
    )
    for enum_name, (table, column, _, old_values) in _ENUM_CHANGES.items():
        values = ", ".join(f"'{value}'" for value in old_values)
        op.execute(
            f"""
            DO $migration$
            BEGIN
                ALTER TYPE {enum_name} RENAME TO {enum_name}_old;
                CREATE TYPE {enum_name} AS ENUM ({values});
                ALTER TABLE {table}
                    ALTER COLUMN {column} TYPE {enum_name}
                    USING {column}::text::{enum_name};
                DROP TYPE {enum_name}_old;
            END $migration$;
            """
        )
    op.execute(
        "ALTER TABLE notification_alert_threshold "
        "ADD CONSTRAINT ck_notification_alert_threshold_percent "
        "CHECK (unit <> 'PERCENT' OR band_value <= 100);"
    )
