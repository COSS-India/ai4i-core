"""create_notification_catalog_table

Adds configs_notification_alert — the notification catalog described in the
Notifications and Alerts design (rev 3, 2026-09-08). One row per notification
type. recipient_roles is its own jsonb column; config holds only thresholds
(ALERT-type rows) — kept separate so "who gets it" and "when it fires" are
independently queryable/patchable, and neither can silently blank the other
on write. Nothing existing is altered.

Scoped to the four enums and the one column set the "Define Notifications"
ticket needs. notification_alert_name_enum holds only the 7 NOTIFICATION-type
values that ticket lists — the two ALERT-type values (QUOTA_THRESHOLD,
BUDGET_THRESHOLD) and the ledger_notification_alert table belong to a later
ticket's migration; Postgres enums are additive (ALTER TYPE ... ADD VALUE), so
extending this one later is cheap.

Revision ID: b72ca7d83df6
Revises: b1c2d3e4f5a6
Create Date: 2026-09-09 00:00:00.000000

Rebased onto b1c2d3e4f5a6 (add_tier_status, PR #1571) — both this migration
and that one originally branched off 6144f82e9ad3, which would have left two
heads once both land on release-2.7. Chaining after theirs instead of
6144f82e9ad3 directly resolves that without either PR needing a rebase once
merged. If #1571 lands first, this needs no further change; if this PR lands
first, whoever rebases #1571 should point it at this branch's new head
instead.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b72ca7d83df6'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NAME_ENUM = "notification_alert_name_enum"
TYPE_ENUM = "notification_alert_type_enum"
MODULE_ENUM = "notification_alert_module_enum"
CHANNEL_ENUM = "notification_alert_channel_enum"

_NAME_VALUES = [
    "TIER_ASSIGNED",
    "TIER_CHANGED",
    "BUDGET_ASSIGNED",
    "BUDGET_UPDATED",
    "QUOTA_LIMIT_UPDATED",
    "QUOTA_EXHAUSTED",
    "BUDGET_EXHAUSTED",
]
_TYPE_VALUES = ["NOTIFICATION", "ALERT"]
_MODULE_VALUES = ["TIER", "BUDGET", "QUOTA"]
# All four declared now so turning one on later is a seed update rather than
# an ALTER TYPE outside a transaction.
_CHANNEL_VALUES = ["EMAIL", "SMS", "SLACK", "WHATSAPP"]


def upgrade() -> None:
    bind = op.get_bind()
    # create_type=False on every column-level reference below: the enum type
    # is created exactly once, here, rather than a second time when
    # create_table() dispatches its own (checkfirst-less) CREATE TYPE for
    # each ENUM-typed column.
    name_enum = postgresql.ENUM(*_NAME_VALUES, name=NAME_ENUM)
    type_enum = postgresql.ENUM(*_TYPE_VALUES, name=TYPE_ENUM)
    module_enum = postgresql.ENUM(*_MODULE_VALUES, name=MODULE_ENUM)
    channel_enum = postgresql.ENUM(*_CHANNEL_VALUES, name=CHANNEL_ENUM)
    name_enum.create(bind, checkfirst=True)
    type_enum.create(bind, checkfirst=True)
    module_enum.create(bind, checkfirst=True)
    channel_enum.create(bind, checkfirst=True)

    name_enum = postgresql.ENUM(*_NAME_VALUES, name=NAME_ENUM, create_type=False)
    type_enum = postgresql.ENUM(*_TYPE_VALUES, name=TYPE_ENUM, create_type=False)
    module_enum = postgresql.ENUM(*_MODULE_VALUES, name=MODULE_ENUM, create_type=False)
    channel_enum = postgresql.ENUM(*_CHANNEL_VALUES, name=CHANNEL_ENUM, create_type=False)

    op.create_table(
        "configs_notification_alert",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", name_enum, nullable=False),
        sa.Column("type", type_enum, nullable=False),
        sa.Column("module", module_enum, nullable=False),
        sa.Column(
            "channels",
            postgresql.ARRAY(channel_enum),
            nullable=False,
            server_default="{EMAIL}",
        ),
        sa.Column("recipient_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_configs_notification_alert_name"),
        sa.CheckConstraint("cardinality(channels) > 0", name="ck_configs_notification_alert_channels"),
    )
    op.create_index(
        "ix_configs_notification_alert_channels",
        "configs_notification_alert",
        ["channels"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_configs_notification_alert_channels", table_name="configs_notification_alert")
    op.drop_table("configs_notification_alert")
    for enum_name in (NAME_ENUM, TYPE_ENUM, MODULE_ENUM, CHANNEL_ENUM):
        op.execute(f"DROP TYPE {enum_name}")
