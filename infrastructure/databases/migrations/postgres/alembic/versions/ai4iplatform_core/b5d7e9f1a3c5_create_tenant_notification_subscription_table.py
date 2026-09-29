"""create_tenant_notification_subscription_table

Adds tenant_notification_subscription — one row per (notification, tenant),
tracking whether that institution is subscribed to an INSTITUTION-scope
catalog row and who its additional recipients are. Row absence for a pair
also means "unsubscribed"; the seed migration
(c6e8f0a2b4d6_seed_tenant_notification_subscriptions) inserts one row per
existing tenant per catalog row anyway so every read has something to join
against.

No FK on tenant_id — tenants live in ai4iplatform_auth, a different
Postgres database, so no cross-database FK is possible (same convention as
ledger_notification_alert.tenant_id, String(255), no FK).

Revision ID: b5d7e9f1a3c5
Revises: e2a4c6b8d0f2
Create Date: 2026-09-25 00:00:00.000001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b5d7e9f1a3c5'
down_revision: Union[str, None] = 'e2a4c6b8d0f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_notification_subscription",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("subscribed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "recipients",
            postgresql.ARRAY(sa.String(length=255)),
            nullable=False,
            server_default="{}",
        ),
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
            name="fk_tenant_notification_subscription_notification_id",
        ),
        sa.UniqueConstraint(
            "notification_id", "tenant_id",
            name="uq_tenant_notification_subscription_identity",
        ),
    )
    op.create_index(
        "ix_tenant_notification_subscription_tenant_id",
        "tenant_notification_subscription",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_notification_subscription_tenant_id",
        table_name="tenant_notification_subscription",
    )
    op.drop_table("tenant_notification_subscription")
