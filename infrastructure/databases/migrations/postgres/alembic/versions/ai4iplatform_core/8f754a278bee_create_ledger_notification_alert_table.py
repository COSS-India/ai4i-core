"""create_ledger_notification_alert_table

Adds ledger_notification_alert — one evolving row per
(notification_id, tenant_id, subject, channel), updated in place rather than
inserted per occurrence (see skills/notification-kafka-design/
notification-kafka-design.md, sections 5-7 for the full design and the
insert-or-update-guarded-by-a-condition mechanism this table is built for).

No seed data — this table starts empty; rows are created and updated only by
Kafka Consumer Notification at runtime.

Revision ID: 8f754a278bee
Revises: 6dc231d5809a
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8f754a278bee'
down_revision: Union[str, None] = '6dc231d5809a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHANNEL_ENUM = "notification_alert_channel_enum"


def upgrade() -> None:
    # Reuses the channel enum type created by b72ca7d83df6 —
    # create_type=False, no CREATE TYPE here.
    channel_enum = postgresql.ENUM(
        "EMAIL", "SMS", "SLACK", "WHATSAPP", name=CHANNEL_ENUM, create_type=False
    )

    op.create_table(
        "ledger_notification_alert",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("channel", channel_enum, nullable=False),
        sa.Column("status", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["configs_notification_alert.id"],
            name="fk_ledger_notification_alert_notification_id",
        ),
        sa.UniqueConstraint(
            "notification_id", "tenant_id", "subject", "channel",
            name="uq_ledger_notification_alert_identity",
        ),
    )
    op.create_index(
        "ix_ledger_notification_alert_notification_id",
        "ledger_notification_alert",
        ["notification_id"],
    )
    op.create_index(
        "ix_ledger_notification_alert_tenant",
        "ledger_notification_alert",
        ["tenant_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ledger_notification_alert_tenant", table_name="ledger_notification_alert")
    op.drop_index("ix_ledger_notification_alert_notification_id", table_name="ledger_notification_alert")
    op.drop_table("ledger_notification_alert")
