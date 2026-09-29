"""add_scope_to_notification_catalog

Adds configs_notification_alert.scope — GLOBAL (applies platform-wide, no
per-institution opt-out) or INSTITUTION (available for an institution to
subscribe to via tenant_notification_subscription, added in
b5d7e9f1a3c5_create_tenant_notification_subscription_table). Per the
Notifications & Alerts scope design: TIER_ASSIGNED and BUDGET_ASSIGNED
default to INSTITUTION; every other catalog row defaults to GLOBAL.

Deliberately does NOT drop recipient_roles: the shared producer-side cache
(libs/ai4i_core/ai4i_core/kafka/notification_settings_cache.py) and
kafka-consumers' catalog_cache.py both still raw-SELECT recipient_roles in
the same query as id/channels/config — dropping it here would fail that
whole query (not just the recipient lookup), silently stopping every
notification/alert send. recipient_roles is dropped only in the follow-up
that moves those readers onto scope + tenant_notification_subscription.

Also backfills recipient_roles["ADMIN"] from the same scope every row just
got: true on GLOBAL rows, false on INSTITUTION rows. Every row was seeded
with recipient_roles = {} (1d3f8e77bac4/6dc231d5809a), so without this,
"the Adopter Admin recipient defaults to selected" would only be true on
screen — app.services.notification_management.catalog_service._to_catalog_item
would derive ADMIN: true for display, but is_notification_enabled (both
producer-side caches) and the consumer's handler.py gate read the stored
{} and would send nothing for all 7 GLOBAL rows until each one happened to
be PATCHed. The stored value is what the send path reads; catalog_service
returns it as-is rather than re-deriving it on every GET, so a row can't
show one thing and send another.

Revision ID: e2a4c6b8d0f2
Revises: d2e4f6a8b0c2
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e2a4c6b8d0f2'
down_revision: Union[str, None] = 'd2e4f6a8b0c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCOPE_ENUM = "notification_alert_scope_enum"
_SCOPE_VALUES = ["GLOBAL", "INSTITUTION"]
# Per the scope design's default table — every other seeded name is GLOBAL.
_INSTITUTION_SCOPE_NAMES = ["TIER_ASSIGNED", "BUDGET_ASSIGNED"]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("configs_notification_alert")}

    if "scope" not in existing_columns:
        scope_enum = postgresql.ENUM(*_SCOPE_VALUES, name=SCOPE_ENUM)
        scope_enum.create(conn, checkfirst=True)
        scope_enum = postgresql.ENUM(*_SCOPE_VALUES, name=SCOPE_ENUM, create_type=False)

        op.add_column(
            "configs_notification_alert",
            sa.Column("scope", scope_enum, nullable=False, server_default="GLOBAL"),
        )
        names = ",".join(f"'{name}'" for name in _INSTITUTION_SCOPE_NAMES)
        op.execute(
            f"UPDATE configs_notification_alert SET scope = 'INSTITUTION' WHERE name IN ({names});"
        )

        # Backfill recipient_roles["ADMIN"] from the scope every row just
        # got, so the send path (which reads recipient_roles, not scope)
        # agrees with the catalog UI from the moment this migration lands
        # — not only once each row happens to be PATCHed. jsonb `||` merges
        # in the key without disturbing any other role already stored.
        op.execute(
            "UPDATE configs_notification_alert "
            "   SET recipient_roles = recipient_roles || '{\"ADMIN\": true}'::jsonb "
            " WHERE scope = 'GLOBAL';"
        )
        op.execute(
            "UPDATE configs_notification_alert "
            "   SET recipient_roles = recipient_roles || '{\"ADMIN\": false}'::jsonb "
            " WHERE scope = 'INSTITUTION';"
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("configs_notification_alert")}

    if "scope" in existing_columns:
        # Mirrors the backfill above — jsonb `-` removes just the one key
        # this migration added, leaving any other role untouched.
        op.execute("UPDATE configs_notification_alert SET recipient_roles = recipient_roles - 'ADMIN';")
        op.drop_column("configs_notification_alert", "scope")
        op.execute(f"DROP TYPE IF EXISTS {SCOPE_ENUM}")
