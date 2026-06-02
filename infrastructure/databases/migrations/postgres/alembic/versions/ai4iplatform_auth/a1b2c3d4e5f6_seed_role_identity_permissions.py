"""seed_role_identity_permissions

Revision ID: a1b2c3d4e5f6
Revises: 9fc0a999caa1
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    conn = op.get_bind()

    # Insert role identity permissions: ADMIN=1, MODERATOR=2, GUEST=3, USER=4, TENANT_ADMIN=5
    identity_permissions = [
        (1, "admin",        "admin",        "admin"),
        (2, "moderator",    "moderator",    "moderator"),
        (3, "guest",        "guest",        "guest"),
        (4, "user",         "user",         "user"),
        (5, "tenant_admin", "tenant_admin", "tenant_admin"),
    ]

    for pid, name, resource, action in identity_permissions:
        conn.execute(
            sa.text("""
                INSERT INTO permissions (id, name, resource, action, created_by)
                VALUES (:id, :name, :resource, :action, :created_by)
                ON CONFLICT (id) DO NOTHING
            """),
            {"id": pid, "name": name, "resource": resource, "action": action, "created_by": SEEDER_ID},
        )

    # Map each role to its identity permission
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r
        JOIN permissions p ON (
            (r.name = 'ADMIN'        AND p.id = 1) OR
            (r.name = 'MODERATOR'    AND p.id = 2) OR
            (r.name = 'GUEST'        AND p.id = 3) OR
            (r.name = 'USER'         AND p.id = 4) OR
            (r.name = 'TENANT ADMIN' AND p.id = 5)
        )
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permission rp
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
        )
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Remove role identity permission mappings
    conn.execute(sa.text("""
        DELETE FROM role_permission
        WHERE permission_id IN (1, 2, 3, 4, 5)
          AND role_id IN (SELECT id FROM roles WHERE name IN ('ADMIN', 'MODERATOR', 'GUEST', 'USER', 'TENANT ADMIN'))
    """))

    # Remove identity permissions 2-5 (leave 1 since seed_default_data already had it)
    conn.execute(sa.text("""
        DELETE FROM permissions WHERE id IN (2, 3, 4, 5)
    """))
