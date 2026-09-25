"""seed_tenant_notification_subscriptions

Seeds tenant_notification_subscription with one row per (existing tenant,
catalog row), subscribed=false, recipients=[that tenant's admin user id] —
so every institution starts unsubscribed from every catalog item (GLOBAL or
INSTITUTION alike; a GLOBAL row's effective subscription is still always
"on", computed from scope at read time, never from this stored bit) with
its own Institution Admin already in place as the default recipient.

Tenants and their admin users live in ai4iplatform_auth — a different
Postgres database from this one (ai4iplatform_core), so no in-database JOIN
is possible. This opens a second, one-off connection via
migration_registry.get_sync_url("ai4iplatform_auth") — the same
cross-database technique services/kafka-consumers/consumers/
notifications_consumer/recipients.py uses at runtime (users JOIN user_role
JOIN roles, filtered to TENANT ADMIN, active, non-deleted) — and reads the
tenant list once, in Python, rather than joining in SQL.

Kept as its own revision from the table DDL so the data can be rolled back
and re-applied without touching the table, matching this repo's existing
seed pattern (see 1d3f8e77bac4_seed_notification_catalog.py).

Revision ID: c6e8f0a2b4d6
Revises: b5d7e9f1a3c5
Create Date: 2026-09-25 00:00:00.000002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import create_engine

from migration_registry import get_sync_url

# revision identifiers, used by Alembic.
revision: str = 'c6e8f0a2b4d6'
down_revision: Union[str, None] = 'b5d7e9f1a3c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TENANT_ADMIN_QUERY = """
    SELECT t.id AS tenant_id,
           (
               SELECT u.id
                 FROM users u
                 JOIN user_role ur ON ur.user_id = u.id
                 JOIN roles r ON r.id = ur.role_id
                WHERE r.name = 'TENANT ADMIN'
                  AND u.tenant_id = t.id
                  AND u.is_delete IS NOT TRUE
                  AND u.is_active IS TRUE
                ORDER BY u.id
                LIMIT 1
           ) AS admin_user_id
      FROM tenants t
"""


def upgrade() -> None:
    conn = op.get_bind()
    notification_ids = [
        row[0] for row in conn.execute(sa.text("SELECT id FROM configs_notification_alert")).fetchall()
    ]
    if not notification_ids:
        return

    auth_engine = create_engine(get_sync_url("ai4iplatform_auth"))
    try:
        with auth_engine.connect() as auth_conn:
            tenant_rows = auth_conn.execute(sa.text(_TENANT_ADMIN_QUERY)).fetchall()
    finally:
        auth_engine.dispose()

    insert_stmt = sa.text(
        "INSERT INTO tenant_notification_subscription"
        "    (notification_id, tenant_id, subscribed, recipients)"
        " VALUES (:notification_id, :tenant_id, false, :recipients)"
        " ON CONFLICT (notification_id, tenant_id) DO NOTHING"
    )
    for tenant_id, admin_user_id in tenant_rows:
        recipients = [str(admin_user_id)] if admin_user_id is not None else []
        for notification_id in notification_ids:
            conn.execute(
                insert_stmt,
                {
                    "notification_id": notification_id,
                    "tenant_id": str(tenant_id),
                    "recipients": recipients,
                },
            )


def downgrade() -> None:
    # This table has no CRUD-create surface (only PATCH/PUT on existing
    # rows) — every row in it originated from this seed, so a full delete
    # is the correct undo, not a targeted one.
    op.execute("DELETE FROM tenant_notification_subscription;")
