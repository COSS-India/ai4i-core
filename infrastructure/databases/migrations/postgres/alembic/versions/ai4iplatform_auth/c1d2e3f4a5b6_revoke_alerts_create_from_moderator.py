"""Revoke alerts.create from MODERATOR role

Per RBAC requirements (PO-confirmed), Alert Definition creation is restricted to
authorized roles (ADMIN). MODERATOR was granted alerts.create (117) by the seed
(2362774ac241), so POST /api/v1/alerts/definitions (gated on alerts.create at the
gateway) returned 201 for moderators instead of 403.

This migration removes alerts.create (117) from MODERATOR. It owns the change for
ALL databases — the seed is intentionally left untouched (never edit an applied
migration); on a fresh DB this runs after the seed and removes the grant, and it
fixes already-seeded databases too. Idempotent: the DELETE is a no-op if absent.

NOTE: MODERATOR still retains alerts.update (118) and alerts.delete (119) — i.e.
moderators can still edit/delete alert definitions, receivers and routing rules.
If the intent is that all alert *writes* are admin-only, add those two perms to
_REVOKED_PERMISSIONS below (pending PO confirmation; out of this ticket's scope).

Revision ID: c1d2e3f4a5b6
Revises: b7e1c2d3f4a5
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b7e1c2d3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

_REVOKED_PERMISSIONS = (
    'alerts.create',
)


def upgrade() -> None:
    conn = op.get_bind()
    for perm_name in _REVOKED_PERMISSIONS:
        conn.execute(sa.text("""
            DELETE FROM role_permission
            WHERE role_id       = (SELECT id FROM roles       WHERE name = 'MODERATOR')
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
