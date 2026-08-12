"""Seed PROGRAM ADMIN role and permission grants.

Permissions granted:
  1   admin (identity sentinel) — platform-core treats this role as admin
  15  users.profile.read        — GET /api/v1/auth/me
  17  users.password.change     — POST /api/v1/auth/change-password
  133 metering.read             — metering dashboard endpoints
  134 usage.read                — PPU usage-summary, usage-tenants
  135 usage.tenant_read         — PPU usage-tenant

Revision ID: a3b4c5d6e7f8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"
ROLE_NAME = "PROGRAM ADMIN"

# Permissions 1, 15, 17 are guaranteed to exist from the main seeder.
# 133, 134, 135 are inserted here so this migration is self-sufficient.
ENSURE_PERMISSIONS = [
    (133, "metering.read",     "metering", "read"),
    (134, "usage.read",        "usage",    "read"),
    (135, "usage.tenant_read", "usage",    "tenant_read"),
]

GRANT_PERMISSION_NAMES = [
    "admin",
    "users.profile.read",
    "users.password.change",
    "metering.read",
    "usage.read",
    "usage.tenant_read",
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Insert PROGRAM ADMIN role.
    conn.execute(
        sa.text("""
            INSERT INTO roles (name, description, created_by)
            VALUES (:name, :description, :created_by)
            ON CONFLICT (name) DO NOTHING
        """),
        {
            "name": ROLE_NAME,
            "description": "Program administrator with usage dashboard access only",
            "created_by": SEEDER_ID,
        },
    )

    # 2. Ensure permissions 133, 134, 135 exist.
    for pid, name, resource, action in ENSURE_PERMISSIONS:
        conn.execute(
            sa.text("""
                INSERT INTO permissions (id, name, resource, action, created_by)
                VALUES (:id, :name, :resource, :action, :created_by)
                ON CONFLICT (id) DO NOTHING
            """),
            {"id": pid, "name": name, "resource": resource, "action": action, "created_by": SEEDER_ID},
        )
    conn.execute(sa.text(
        "SELECT setval(pg_get_serial_sequence('permissions', 'id'),"
        " GREATEST((SELECT MAX(id) FROM permissions), 135))"
    ))

    # 3. Grant all permissions to PROGRAM ADMIN by name.
    conn.execute(
        sa.text(f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name = ANY(:names)
            WHERE r.name = :role_name
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """),
        {"names": GRANT_PERMISSION_NAMES, "role_name": ROLE_NAME},
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE role_id = (SELECT id FROM roles WHERE name = :role_name)
    """), {"role_name": ROLE_NAME})

    conn.execute(sa.text("DELETE FROM roles WHERE name = :role_name"), {"role_name": ROLE_NAME})
