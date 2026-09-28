"""create_notification_failures_table

Adds notification_failures — one row per notification email that never
went out to any recipient. notifications_consumer no longer touches
ledger_notification_alert at all (per review: consumer should be dumb,
no dedup/state-tracking); this is its own, separate record of delivery
failures only.

By design this holds only the two columns the consumer actually writes:
the entire failed Kafka message, verbatim, and the channel it failed on.
No FK, no per-event parsing of that message — notifications_consumer
deliberately doesn't interpret its own envelopes any more than this table
does.

Revision ID: 5d8b9c5ac075
Revises: bcdd3516d0ab
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5d8b9c5ac075'
down_revision: Union[str, None] = 'bcdd3516d0ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_failures",
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_failures")
