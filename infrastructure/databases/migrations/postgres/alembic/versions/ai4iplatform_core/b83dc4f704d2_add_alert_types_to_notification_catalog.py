"""add_alert_types_to_notification_catalog

Extends notification_alert_name_enum with the 2 ALERT-type values the
"Define Alerts" ticket needs: QUOTA_THRESHOLD and BUDGET_THRESHOLD. Deferred
out of b72ca7d83df6_create_notification_catalog_table on purpose — see that
migration's docstring — because Postgres enums are additive, so this is the
cheap follow-up it anticipated rather than a rewrite.

No existing row, column or table is touched. configs_notification_alert
already declares notification_alert_name_enum with create_type=False, so
extending the type here is enough — no ALTER TABLE needed.

Kept separate from the seed migration (seed_alert_catalog_types) for the same
reason 1d3f8e77bac4 was split from b72ca7d83df6: a newly added enum value
cannot be referenced (e.g. in an INSERT) in the same transaction that adds
it, on the Postgres versions this platform supports.

Revision ID: b83dc4f704d2
Revises: 1d3f8e77bac4
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b83dc4f704d2'
down_revision: Union[str, None] = '1d3f8e77bac4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NAME_ENUM = "notification_alert_name_enum"
_NEW_VALUES = ["QUOTA_THRESHOLD", "BUDGET_THRESHOLD"]


def upgrade() -> None:
    for value in _NEW_VALUES:
        # Guarded the same way 53a41e6233f1 (auth-service) adds an enum
        # value: ALTER TYPE ... ADD VALUE isn't idempotent on its own, and
        # this migration must be safe to run against a database where it
        # partially applied.
        op.execute(
            f"""
            DO $migration$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_enum e
                    JOIN pg_type t ON e.enumtypid = t.oid
                    WHERE t.typname = '{NAME_ENUM}'
                      AND e.enumlabel = '{value}'
                ) THEN
                    ALTER TYPE {NAME_ENUM} ADD VALUE '{value}';
                END IF;
            END $migration$;
            """
        )


def downgrade() -> None:
    # Postgres cannot drop a single enum value. Rebuild the type without the
    # 2 ALERT values, same technique as 53a41e6233f1's downgrade. Assumes the
    # seed migration's downgrade (which deletes the 2 ALERT rows) has already
    # run — the normal alembic downgrade order, since it revises this one.
    op.execute(
        f"""
        DO $migration$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = '{NAME_ENUM}') THEN
                ALTER TYPE {NAME_ENUM} RENAME TO {NAME_ENUM}_old;
            END IF;
            CREATE TYPE {NAME_ENUM} AS ENUM (
                'TIER_ASSIGNED', 'TIER_CHANGED', 'BUDGET_ASSIGNED', 'BUDGET_UPDATED',
                'QUOTA_LIMIT_UPDATED', 'QUOTA_EXHAUSTED', 'BUDGET_EXHAUSTED'
            );
            ALTER TABLE configs_notification_alert
                ALTER COLUMN name TYPE {NAME_ENUM}
                USING name::text::{NAME_ENUM};
            DROP TYPE IF EXISTS {NAME_ENUM}_old;
        END $migration$;
        """
    )
