"""Revoke user-management permissions from MODERATOR role

MODERATOR should not be able to read role assignments, list/update tenant users,
or update tenant user profiles — those operations are scoped to ADMIN and TENANT ADMIN.

Removes from MODERATOR:
  - roles.read  (20): gates GET /auth/roles/list, GET /auth/roles/user/{id}
  - tenant.users.read   (44): gates GET /tenants/{id}/users
  - tenant.users.update (46): gates PATCH /tenants/{id}/users/{id}/status,
                                     PATCH /tenants/{id}/users/{id}

The seed migration (2362774ac241) is updated in parallel so fresh installs are
correct. This migration fixes already-seeded databases.

Idempotent: DELETE WHERE is a no-op if the rows are absent.

Re-parented from d7a1c3f9e2b4 onto e1f8a2c4b903 to linearize the two
ai4iplatform_auth heads that both branched off d7a1c3f9e2b4 (this revoke +
e1f8a2c4b903 grant). Both are independent role_permission data changes, so
order is immaterial; linearizing makes `alembic upgrade head` unambiguous.

Revision ID: e3f4a5b6c7d8
Revises: e1f8a2c4b903
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'e1f8a2c4b903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

_REVOKED_PERMISSIONS = (
    'roles.read',
    'tenant.users.read',
    'tenant.users.update',
)


def upgrade() -> None:
    conn = op.get_bind()
    for perm_name in _REVOKED_PERMISSIONS:
        conn.execute(sa.text("""
            DELETE FROM role_permission
            WHERE role_id    = (SELECT id FROM roles       WHERE name = 'MODERATOR')
              AND permission_id = (SELECT id FROM permissions WHERE name = :perm)
        """), {"perm": perm_name})


def downgrade() -> None:
    conn = op.get_bind()
    for perm_name in _REVOKED_PERMISSIONS:
        conn.execute(sa.text("""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, :seeder_id
            FROM roles r
            JOIN permissions p ON p.name = :perm
            WHERE r.name = 'MODERATOR'
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """), {"perm": perm_name, "seeder_id": SEEDER_ID})
