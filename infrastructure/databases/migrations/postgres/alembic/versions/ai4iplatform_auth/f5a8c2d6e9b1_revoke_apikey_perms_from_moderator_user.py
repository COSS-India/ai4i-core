"""Revoke API-key permissions (30-33) from MODERATOR and USER roles

Per RBAC spec: only ADMIN and TENANT ADMIN are allowed to manage API keys.
MODERATOR and USER were incorrectly seeded with the full apiKey.{create,read,
update,delete} set, which let them hit POST/GET/PATCH/DELETE /api/v1/auth/api-keys.

This migration removes those four permissions from MODERATOR and USER on
already-seeded DBs. The seed migration (2362774ac241) is updated in parallel
so fresh installs no longer grant them.

This also functions as a **merge migration**: the auth-schema graph had two
heads (e1f8a2c4b903, e3f4a5b6c7d8) both branched off d7a1c3f9e2b4. Closing
the branch here means ``alembic upgrade head`` no longer fails with
"multiple heads".

Idempotent: ``DELETE … WHERE`` is a no-op when the rows are already absent.

Revision ID: f5a8c2d6e9b1
Revises: e1f8a2c4b903, e3f4a5b6c7d8
Create Date: 2026-06-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f5a8c2d6e9b1'
# Tuple == merge migration; closes both heads created on 2026-06-01.
down_revision: Union[str, Sequence[str], None] = ('e1f8a2c4b903', 'e3f4a5b6c7d8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

_REVOKED_ROLES = ('MODERATOR', 'USER')
_REVOKED_PERMISSIONS = (
    'apiKey.create',   # id 30 — gates POST /api/v1/auth/api-keys
    'apiKey.read',     # id 31 — gates GET  /api/v1/auth/api-keys
    'apiKey.update',   # id 32 — gates PATCH /api/v1/auth/api-keys/{api_key}
    'apiKey.delete',   # id 33 — gates DELETE /api/v1/auth/api-keys/{api_key}
)


def upgrade() -> None:
    conn = op.get_bind()
    for role_name in _REVOKED_ROLES:
        for perm_name in _REVOKED_PERMISSIONS:
            conn.execute(
                sa.text(
                    """
                    DELETE FROM role_permission
                    WHERE role_id       = (SELECT id FROM roles       WHERE name = :role)
                      AND permission_id = (SELECT id FROM permissions WHERE name = :perm)
                    """
                ),
                {"role": role_name, "perm": perm_name},
            )


def downgrade() -> None:
    conn = op.get_bind()
    for role_name in _REVOKED_ROLES:
        for perm_name in _REVOKED_PERMISSIONS:
            # Re-grant only if not already present — role_permission has no
            # unique constraint, so a naive INSERT would double-grant.
            conn.execute(
                sa.text(
                    """
                    INSERT INTO role_permission (role_id, permission_id, created_by)
                    SELECT r.id, p.id, :seeder_id
                    FROM roles r
                    JOIN permissions p ON p.name = :perm
                    WHERE r.name = :role
                      AND NOT EXISTS (
                          SELECT 1 FROM role_permission rp
                          WHERE rp.role_id = r.id AND rp.permission_id = p.id
                      )
                    """
                ),
                {"role": role_name, "perm": perm_name, "seeder_id": SEEDER_ID},
            )
