"""Grant policies.read (permission 100) to ADMIN and TENANT ADMIN.

List-policies was previously gated behind the admin-only sentinel (permission 1)
in api_permissions.json. Changing it to permission 100 (policies.read) lets
tenant admins view the policy catalogue so they can subscribe their applications.

Revision ID: d1e2f3a4b5c7
Revises: 51379ee0d696
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c7"
down_revision: Union[str, None] = "51379ee0d696"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

PERMISSIONS = [
    (100, "policies.read", "policies", "read"),
]

GRANTED_ROLES = ("ADMIN", "TENANT ADMIN")


def upgrade() -> None:
    conn = op.get_bind()

    for perm_id, name, resource, action in PERMISSIONS:
        conn.execute(
            sa.text("""
                INSERT INTO permissions (id, name, resource, action, created_by)
                SELECT :perm_id, :name, :resource, :action, :seeder_id
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = :name)
            """),
            {"perm_id": perm_id, "name": name, "resource": resource,
             "action": action, "seeder_id": SEEDER_ID},
        )
        conn.execute(
            sa.text(
                "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
                " GREATEST((SELECT MAX(id) FROM permissions), :perm_id))"
            ),
            {"perm_id": perm_id},
        )
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
    # Only remove the TENANT ADMIN grant — the permission row and ADMIN's grant
    # both pre-exist from 2362774ac241_seed_default_data and must stay in place.
    conn.execute(
        sa.text("""
            DELETE FROM role_permission
            WHERE permission_id IN (SELECT id FROM permissions WHERE name = ANY(:names))
              AND role_id IN (SELECT id FROM roles WHERE name = 'TENANT ADMIN')
        """),
        {"names": names},
    )
