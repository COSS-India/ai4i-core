"""Add application.create (43) / application.read (48) / application.update (49);
grant to ADMIN and TENANT ADMIN only.

Application Management is an Institution Admin action, with Adopter Admin
able to act on any Institution as the higher-role edge case (see
ApplicationService._authorize in auth-service). MODERATOR is deliberately
excluded — unlike tenant.users.* operations, which MODERATOR can perform
except delete, Application Management is not part of a Moderator's remit.

Ids 43/48/49 were reserved in api_permissions.json ahead of this migration
(the tenant.* block already occupies 40/41/42/44/45/46/47, leaving 43/48/49
free) — see POST/GET/PATCH .../applications entries there.

Revision ID: c2d3e4f5a6b7
Revises: a9b8c7d6e5f4
Create Date: 2026-08-27 00:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

PERMISSIONS = [
    (43, "application.create", "application", "create"),
    (48, "application.read", "application", "read"),
    (49, "application.update", "application", "update"),
]

GRANTED_ROLES = ("ADMIN", "TENANT ADMIN")


def upgrade() -> None:
    conn = op.get_bind()

    for perm_id, name, resource, action in PERMISSIONS:
        conn.execute(
            sa.text("""
                INSERT INTO permissions (id, name, resource, action, created_by)
                SELECT :perm_id, :name, :resource, :action, :seeder_id
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE id = :perm_id)
                  AND NOT EXISTS (SELECT 1 FROM permissions WHERE name = :name)
            """),
            {
                "perm_id": perm_id,
                "name": name,
                "resource": resource,
                "action": action,
                "seeder_id": SEEDER_ID,
            },
        )
        conn.execute(sa.text(
            "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
            " GREATEST((SELECT MAX(id) FROM permissions), :perm_id))"
        ), {"perm_id": perm_id})

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
            {"name": name, "roles": list(GRANTED_ROLES), "seeder_id": SEEDER_ID},
        )


def downgrade() -> None:
    conn = op.get_bind()
    names = [p[1] for p in PERMISSIONS]
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE permission_id IN (SELECT id FROM permissions WHERE name = ANY(:names))
          AND role_id IN (SELECT id FROM roles WHERE name = ANY(:roles))
    """), {"names": names, "roles": list(GRANTED_ROLES)})
    conn.execute(sa.text(
        "DELETE FROM permissions WHERE name = ANY(:names)"
    ), {"names": names})
