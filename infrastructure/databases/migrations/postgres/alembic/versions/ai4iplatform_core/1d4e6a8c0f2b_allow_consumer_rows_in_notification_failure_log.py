"""allow_consumer_rows_in_notification_failure_log

notifications_consumer records its delivery failures in
notification_alert_failure_log (0c96d7881ce5) too — one row per event that
reached no recipient on any channel. Two things the table did not allow yet:

* stage — new DELIVERY value on notification_failure_stage_enum.
* producer — 'notifications-consumer' added to ck_failure_log_producer.

The consumer does not know the catalog id, so its rows leave
notification_id NULL.

ADD VALUE runs outside the migration's transaction (autocommit_block, which
needs env.py's transaction_per_migration=True). Postgres cannot drop an enum
value, so the downgrade leaves DELIVERY in the type; it only removes the
consumer's rows and restores the old CHECK.

Revision ID: 1d4e6a8c0f2b
Revises: 0c96d7881ce5
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1d4e6a8c0f2b'
down_revision: Union[str, None] = '0c96d7881ce5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FAILURE_LOG_TABLE = "notification_alert_failure_log"
FAILURE_STAGE_ENUM = "notification_failure_stage_enum"
PRODUCER_CHECK = "ck_failure_log_producer"

STAGE_DELIVERY = "DELIVERY"
CONSUMER = "notifications-consumer"
PRODUCERS = ["auth-service", "platform-core-service", "payperuse-consumer", "monitoring-evaluator"]


def _sql_list(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _set_producer_check(producers) -> None:
    op.drop_constraint(PRODUCER_CHECK, FAILURE_LOG_TABLE, type_="check")
    op.create_check_constraint(PRODUCER_CHECK, FAILURE_LOG_TABLE, f"producer IN ({_sql_list(producers)})")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TYPE {FAILURE_STAGE_ENUM} ADD VALUE IF NOT EXISTS '{STAGE_DELIVERY}'")
    _set_producer_check([*PRODUCERS, CONSUMER])


def downgrade() -> None:
    op.execute(f"DELETE FROM {FAILURE_LOG_TABLE} WHERE producer = '{CONSUMER}'")
    _set_producer_check(PRODUCERS)
