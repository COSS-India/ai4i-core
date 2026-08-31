"""Add usage.application_read (146); grant to ADMIN and TENANT ADMIN.

Backs the Metering Dashboard's Applications tab (AI4IDS-2886):
  GET /api/v1/pay-per-use/usage-applications-summary
  GET /api/v1/pay-per-use/usage-applications
  GET /api/v1/pay-per-use/usage-application
  -> permissionRequired: 146 (usage.application_read)

All three endpoints share one access rule (unlike usage.read(134)/
usage.tenant_read(135), which are split because the platform-wide overview
and the single-tenant detail have genuinely different audiences): Adopter
Admin sees any Institution's Applications, Institution Admin (TENANT ADMIN)
sees only their own Institution's — enforced in-route by
application_usage.py's tenant-scoping check, same as usage-tenant's.id 146
was reserved in api_permissions.json ahead of this migration (145 is the
highest id previously used, per d5e6f7a8b9c0/ppu.tenant.read).

Revision ID: d9e8f7a6b5c4
Revises: c2d3e4f5a6b7
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd9e8f7a6b5c4'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

PERM_ID = 146
PERM_NAME = "usage.application_read"
GRANTED_ROLES = ("ADMIN", "TENANT ADMIN")


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text("""
            INSERT INTO permissions (id, name, resource, action, created_by)
            SELECT :perm_id, :name, 'usage.application', 'read', :seeder_id
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = :name)
        """),
        {"perm_id": PERM_ID, "name": PERM_NAME, "seeder_id": SEEDER_ID},
    )
    conn.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
        " GREATEST((SELECT MAX(id) FROM permissions), :perm_id))"
    ), {"perm_id": PERM_ID})

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
        {"name": PERM_NAME, "roles": list(GRANTED_ROLES), "seeder_id": SEEDER_ID},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE permission_id = (SELECT id FROM permissions WHERE name = :name)
          AND role_id IN (SELECT id FROM roles WHERE name = ANY(:roles))
    """), {"name": PERM_NAME, "roles": list(GRANTED_ROLES)})
    conn.execute(sa.text(
        "DELETE FROM permissions WHERE name = :name"
    ), {"name": PERM_NAME})
