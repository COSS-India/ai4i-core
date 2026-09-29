"""create_monitoring_alert_recipient_table

Adds monitoring_alert_recipient: the resolved user ids a MONITORING-type
catalog row (a2b4d6f8c0e3) is delivered to, one row per (notification,
user). Monitoring alerts have no scope and no tenant — their recipients are
platform users holding the ADMIN (Adopter Admin) and/or MODERATOR role — so
tenant_notification_subscription (keyed per tenant) doesn't fit.

``role`` records which selected role pulled the user in. The monitoring
catalog PATCH (app.services.notification_management.
monitoring_catalog_service) rebuilds a notification's rows wholesale from
configs_notification_alert.recipient_roles every time recipient_roles
changes.

Also backfills: a2b4d6f8c0e3 seeded every monitoring row with
recipient_roles = {"ADMIN": true, "MODERATOR": false}, so without this the
default "Adopter Admin" selection would resolve to nobody until each row
happened to be PATCHed. Users live in ai4iplatform_auth, a different
database — read via a one-off connection, same technique as
c6e8f0a2b4d6_seed_tenant_notification_subscriptions.

Revision ID: b3c5e7a9d1f4
Revises: a2b4d6f8c0e3
Create Date: 2026-09-28 00:00:00.000002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import create_engine

from migration_registry import get_sync_url

# revision identifiers, used by Alembic.
revision: str = 'b3c5e7a9d1f4'
down_revision: Union[str, None] = 'a2b4d6f8c0e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ROLE_USERS_QUERY = """
    SELECT DISTINCT r.name AS role, u.id::text AS user_id
      FROM users u
      JOIN user_role ur ON ur.user_id = u.id
      JOIN roles r ON r.id = ur.role_id
     WHERE r.name IN ('ADMIN', 'MODERATOR')
       AND u.is_delete IS NOT TRUE
       AND u.is_active IS TRUE
     ORDER BY 1, 2
"""


def upgrade() -> None:
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

    conn = op.get_bind()
    # (notification_id, selected roles) for every MONITORING row.
    selections = [
        (row.id, {role for role, on in (row.recipient_roles or {}).items() if on})
        for row in conn.execute(sa.text(
            "SELECT id, recipient_roles FROM configs_notification_alert WHERE type = 'MONITORING'"
        )).fetchall()
    ]
    if not any(roles for _, roles in selections):
        return

    auth_engine = create_engine(get_sync_url("ai4iplatform_auth"))
    try:
        with auth_engine.connect() as auth_conn:
            role_users = auth_conn.execute(sa.text(_ROLE_USERS_QUERY)).fetchall()
    finally:
        auth_engine.dispose()

    insert_stmt = sa.text(
        "INSERT INTO monitoring_alert_recipient (notification_id, user_id, role)"
        " VALUES (:notification_id, :user_id, :role)"
        " ON CONFLICT (notification_id, user_id) DO NOTHING"
    )
    for notification_id, roles in selections:
        for role, user_id in role_users:
            if role in roles:
                conn.execute(
                    insert_stmt,
                    {"notification_id": notification_id, "user_id": user_id, "role": role},
                )


def downgrade() -> None:
    op.drop_index(
        "ix_monitoring_alert_recipient_notification_id",
        table_name="monitoring_alert_recipient",
    )
    op.drop_table("monitoring_alert_recipient")
