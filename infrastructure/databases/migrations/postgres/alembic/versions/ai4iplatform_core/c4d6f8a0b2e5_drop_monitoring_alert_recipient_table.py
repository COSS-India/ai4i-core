"""drop_monitoring_alert_recipient_table

Drops monitoring_alert_recipient (b3c5e7a9d1f4). It froze each MONITORING
row's ADMIN / MODERATOR selection into user ids at PATCH time, and nothing
rebuilt it when a user gained or lost the role or was deactivated — a new
Adopter Admin got no monitoring alerts until someone re-saved the row, and
a revoked user stayed on the list.

Recipients are now resolved at send time from
configs_notification_alert.recipient_roles
(ai4i_core.kafka.recipients.resolve_monitoring_recipients), the same way
metering resolves its recipients per event, so the table has no reader left.

A forward drop rather than deleting b3c5e7a9d1f4: databases that already ran
it (alembic_version = b3c5e7a9d1f4) would otherwise fail with "Can't locate
revision".

Revision ID: c4d6f8a0b2e5
Revises: b3c5e7a9d1f4
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4d6f8a0b2e5'
down_revision: Union[str, None] = 'b3c5e7a9d1f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_monitoring_alert_recipient_notification_id")
    op.execute("DROP TABLE IF EXISTS monitoring_alert_recipient")


def downgrade() -> None:
    # Recreates the empty table only — its rows were a derived snapshot, and
    # b3c5e7a9d1f4's own backfill isn't re-run here.
    op.create_table(
        "monitoring_alert_recipient",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["configs_notification_alert.id"],
            name="fk_monitoring_alert_recipient_notification_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "notification_id", "user_id",
            name="uq_monitoring_alert_recipient_identity",
        ),
    )
    op.create_index(
        "ix_monitoring_alert_recipient_notification_id",
        "monitoring_alert_recipient",
        ["notification_id"],
    )
