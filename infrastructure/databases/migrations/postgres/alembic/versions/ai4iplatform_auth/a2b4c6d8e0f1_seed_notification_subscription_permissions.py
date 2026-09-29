"""Add notification.subscription.read (148) and
notification.subscription.update (149); grant both to ADMIN and TENANT ADMIN.

Backs the Institution Admin metering-notification-subscription endpoints
registered in auth-service/api_permissions.json:
  GET   /api/v1/notification-alerts/subscriptions                    -> permissionRequired: 148 (notification.subscription.read)
  PATCH /api/v1/notification-alerts/subscriptions/{notification_id}  -> permissionRequired: 149 (notification.subscription.update)
  PUT   /api/v1/notification-alerts/subscriptions/{notification_id}  -> permissionRequired: 149 (notification.subscription.update)

Split read/update the same way alerts.read(116)/alerts.create(117)/
alerts.update(118) are, rather than one shared id the way
usage.application_read(146) covers three GET-only endpoints — PATCH and
PUT here are both "modify this institution's subscription" actions on the
same resource, so they share one id; GET is a materially different
capability (view only) and gets its own.

Both ADMIN (Adopter Admin, platform-wide) and TENANT ADMIN (Institution
Admin, own tenant only) can call all three — platform-core-service's
app.core.permissions.authorize_own_tenant_or_admin enforces the "own
tenant only for TENANT ADMIN" scoping in-route, the same split
usage.tenant_read(135)/usage.application_read(146) already rely on.

148 was the next unused id (147 - ppu.tier.status.update - was the
highest previously used, per e0f1a2b3c4d5).

Revision ID: a2b4c6d8e0f1
Revises: f3a9b1c7d2e6
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2b4c6d8e0f1'
down_revision: Union[str, None] = 'f3a9b1c7d2e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

GRANTED_ROLES = ("ADMIN", "TENANT ADMIN")

PERMISSIONS = (
    {"id": 148, "name": "notification.subscription.read", "resource": "notification.subscription", "action": "read"},
    {"id": 149, "name": "notification.subscription.update", "resource": "notification.subscription", "action": "update"},
)


def upgrade() -> None:
    conn = op.get_bind()

    for perm in PERMISSIONS:
        conn.execute(
            sa.text("""
                INSERT INTO permissions (id, name, resource, action, created_by)
                SELECT :id, :name, :resource, :action, :seeder_id
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = :name)
            """),
            {**perm, "seeder_id": SEEDER_ID},
        )
        conn.execute(sa.text(
            "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
            " GREATEST((SELECT MAX(id) FROM permissions), :id))"
        ), {"id": perm["id"]})

        conn.execute(
            sa.text("""
                INSERT INTO role_permission (role_id, permission_id, created_by)
                SELECT r.id, p.id, :seeder_id
                FROM roles r
                JOIN permissions p ON p.name = :name
                WHERE r.name = ANY(:roles)
                  AND NOT EXISTS (
                      SELECT 1 FROM role_permission rp
                      WHERE rp.role_id = r.id AND rp.permission_id = p.id
                  )
            """),
            {"name": perm["name"], "roles": list(GRANTED_ROLES), "seeder_id": SEEDER_ID},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for perm in PERMISSIONS:
        conn.execute(sa.text("""
            DELETE FROM role_permission
            WHERE permission_id = (SELECT id FROM permissions WHERE name = :name)
              AND role_id IN (SELECT id FROM roles WHERE name = ANY(:roles))
        """), {"name": perm["name"], "roles": list(GRANTED_ROLES)})
        conn.execute(sa.text(
            "DELETE FROM permissions WHERE name = :name"
        ), {"name": perm["name"]})
