"""Grant usage.application_read (146) to USAGE VIEWER.

d9e8f7a6b5c4 seeded usage.application_read for ADMIN and TENANT ADMIN only,
so a Usage Viewer opening the Metering Dashboard's Applications tab gets 403
from auth-service validation on all three endpoints (AI4IDS-3239):
  GET /api/v1/pay-per-use/usage-applications-summary
  GET /api/v1/pay-per-use/usage-applications
  GET /api/v1/pay-per-use/usage-application

USAGE VIEWER already holds usage.read (134) and usage.tenant_read (135) for
the rest of the dashboard, plus the admin identity permission (1), so
platform-core-service's authorize_own_tenant_or_admin already lets it view
any institution once the gateway passes the request. Only this grant is
missing.

Revision ID: a4e3128bdf70
Revises: a2b4c6d8e0f1
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a4e3128bdf70'
down_revision: Union[str, None] = 'a2b4c6d8e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

PERM_NAME = "usage.application_read"
ROLE_NAME = "USAGE VIEWER"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, :seeder_id
            FROM roles r
            JOIN permissions p ON p.name = :perm
            WHERE r.name = :role
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """),
        {"perm": PERM_NAME, "role": ROLE_NAME, "seeder_id": SEEDER_ID},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("""
            DELETE FROM role_permission
            WHERE permission_id = (SELECT id FROM permissions WHERE name = :perm)
              AND role_id = (SELECT id FROM roles WHERE name = :role)
        """),
        {"perm": PERM_NAME, "role": ROLE_NAME},
    )
