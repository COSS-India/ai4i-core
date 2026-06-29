"""Add usage.read (134) / usage.tenant_read (135); fix TENANT_ADMIN over-grant

Two separate permissions gate the three usage dashboard endpoints:

  usage.read (134)        — ADMIN, MODERATOR only
    GET /api/v1/usage/summary   (platform-wide aggregate)
    GET /api/v1/usage/tenants   (all-tenant list)

  usage.tenant_read (135) — ADMIN, MODERATOR, TENANT_ADMIN
    GET /api/v1/usage/tenant    (single-tenant detail; TENANT_ADMIN sees own tenant only,
                                 enforced by platform-core via X-Permission-IDS)

Splitting the permissions means the gateway and route-layer checks agree:
TENANT_ADMIN never holds 134 so it cannot reach /summary or /tenants at the
gateway layer, regardless of any future changes to route-level guards.

Revision ID: e5f6a7b8c9d1
Revises: c5d6e7f8a9b0
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d1'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()

    # 1. usage.read (134) — platform-wide usage routes; ADMIN and MODERATOR only.
    conn.execute(
        sa.text("""
            INSERT INTO permissions (id, name, resource, action, created_by)
            SELECT 134, 'usage.read', 'usage', 'read', :seeder_id
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE id = 134)
              AND NOT EXISTS (SELECT 1 FROM permissions WHERE name = 'usage.read')
        """),
        {"seeder_id": SEEDER_ID},
    )
    conn.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
        " GREATEST((SELECT MAX(id) FROM permissions), 134))"
    ))

    conn.execute(
        sa.text("""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, :seeder_id
            FROM roles r
            JOIN permissions p ON p.name = 'usage.read'
            WHERE r.name IN ('ADMIN', 'MODERATOR')
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """),
        {"seeder_id": SEEDER_ID},
    )

    # 2. usage.tenant_read (135) — single-tenant detail route; TENANT_ADMIN included.
    conn.execute(
        sa.text("""
            INSERT INTO permissions (id, name, resource, action, created_by)
            SELECT 135, 'usage.tenant_read', 'usage', 'tenant_read', :seeder_id
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE id = 135)
              AND NOT EXISTS (SELECT 1 FROM permissions WHERE name = 'usage.tenant_read')
        """),
        {"seeder_id": SEEDER_ID},
    )
    conn.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
        " GREATEST((SELECT MAX(id) FROM permissions), 135))"
    ))

    conn.execute(
        sa.text("""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, :seeder_id
            FROM roles r
            JOIN permissions p ON p.name = 'usage.tenant_read'
            WHERE r.name IN ('ADMIN', 'MODERATOR', 'TENANT ADMIN')
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
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE name IN ('usage.read', 'usage.tenant_read')
        )
          AND role_id IN (
            SELECT id FROM roles WHERE name IN ('ADMIN', 'MODERATOR', 'TENANT ADMIN')
        )
    """))
    conn.execute(sa.text(
        "DELETE FROM permissions WHERE name IN ('usage.read', 'usage.tenant_read')"
    ))
