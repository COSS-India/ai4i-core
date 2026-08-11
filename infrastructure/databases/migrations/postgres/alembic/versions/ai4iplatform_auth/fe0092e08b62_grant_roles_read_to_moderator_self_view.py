"""Grant roles.read to MODERATOR for self-view of role assignments

GET /api/v1/auth/roles/user/{user_id} lets a caller view their own role
assignments (self-access only, enforced by require_self_or_any_role in
app/dependencies/permissions.py). MODERATOR previously lacked roles.read,
so the gateway rejected the request before it ever reached the route.

Migration e3f4a5b6c7d8 revoked roles.read from MODERATOR so it could not
read *any* user's role assignments or list all roles. That intent is
preserved here: MODERATOR is not in the privileged-role tuple passed to
require_self_or_any_role in role.py, so this grant only unlocks self-view.
GET /auth/roles/list stays blocked for MODERATOR at the route level
(require_any_role(ADMIN, TENANT_ADMIN)); GET /tenants/{id}/users and
related tenant.users.* endpoints are gated by separate permissions (44, 46)
that this migration does not touch.

roles.read also gates GET /auth/roles/list/guest/services, which has no
route-level role restriction beyond authentication — MODERATOR gains read
access to that list as a side effect. MODERATOR already holds broader
permissions (service.read, model.read, etc.), so this is not a new
capability of consequence.

Idempotent: guarded by NOT EXISTS / DELETE WHERE.

Revision ID: fe0092e08b62
Revises: 6883c437e31e
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fe0092e08b62'
down_revision: Union[str, None] = '6883c437e31e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, :seeder_id
            FROM roles r
            JOIN permissions p ON p.name = 'roles.read'
            WHERE r.name = 'MODERATOR'
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """),
        {"seeder_id": SEEDER_ID},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE role_id IN (SELECT id FROM roles WHERE name = 'MODERATOR')
          AND permission_id IN (SELECT id FROM permissions WHERE name = 'roles.read')
    """))
