"""Grant roles.read to USER role

GET /api/v1/auth/roles/user/{user_id} lets a caller view their own role
assignments (self-access only, enforced in the route). USER previously
lacked roles.read, so the gateway rejected the request with
INSUFFICIENT_PERMISSIONS before it ever reached the route. GUEST already
has roles.read for the same self-access case.

Idempotent: guarded by NOT EXISTS / DELETE WHERE. Applies to fresh installs
and already-seeded databases alike, since the automated migration pipeline
runs every pending revision regardless of when the DB was first seeded.

Revision ID: 6883c437e31e
Revises: a2b3c4d5e6f7
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6883c437e31e'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
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
            WHERE r.name = 'USER'
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
        WHERE role_id IN (SELECT id FROM roles WHERE name = 'USER')
          AND permission_id IN (SELECT id FROM permissions WHERE name = 'roles.read')
    """))
