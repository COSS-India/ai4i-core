"""
Default Admin User Seeder (ai4iplatform_auth)

Creates/updates the default admin user, assigns the ADMIN role, and maps
the user to the default tenant created by auth_service_t_default_tenant_seeder.py.

IMPORTANT: After first login, change the default admin password immediately.
The default password is set via ADMIN_DEFAULT_PASSWORD env var (falls back to 'ADMIN_PASSWORD').

Schema notes:
  - users.id is UUID PK
  - users.tenant_id is Integer FK to tenants.id
  - passwords stored in separate user_credentials table (user_id is unique FK)
  - role assignment via user_role table (no unique constraint on user_id+role_id)
  - creation_type enum values: 'default', 'google'

Rows created by this seeder carry created_by = SEEDER_ID so they can be
distinguished from user-created records.

Runs after auth_service_t_default_tenant_seeder.py (filename order).
"""
import os
import uuid

from infrastructure.databases.core.base_seeder import BaseSeeder
from infrastructure.databases.seeders.postgres.ai4iplatform_auth._seeder_helpers import (
    DEFAULT_TENANT_ORG,
    SEEDER_ID,
    resolve_credentials,
)


class AuthServiceDefaultAdminSeeder(BaseSeeder):
    """Create default admin user for ai4iplatform_auth"""

    database = "ai4iplatform_auth"

    def run(self, adapter):
        default_password = os.getenv("ADMIN_DEFAULT_PASSWORD", "ADMIN_PASSWORD")
        admin_email = "admin@ai4inclusion.org"
        tenant_org = (os.getenv("DEFAULT_TENANT_ORG") or DEFAULT_TENANT_ORG).strip()

        password_hash, salt = resolve_credentials(adapter, admin_email, default_password)

        # Resolve the default tenant id (Integer)
        tenant_row = adapter.fetch_one(
            "SELECT id FROM tenants WHERE organisation = :org LIMIT 1",
            {"org": tenant_org},
        )
        tenant_id = tenant_row[0] if tenant_row else None

        # Upsert user (id is a UUID; preserve existing UUID on conflict)
        new_user_id = str(uuid.uuid4())
        adapter.execute(
            """
            INSERT INTO users (
                id, email, username, full_name,
                is_active, tenant_id, timezone, is_delete, is_tenant_active,
                creation_type, created_by
            )
            VALUES (
                :user_id, :email, :username, :full_name,
                :is_active, :tenant_id, :timezone, :is_delete, :is_tenant_active,
                :creation_type, :created_by
            )
            ON CONFLICT (email) DO UPDATE
            SET
                username         = EXCLUDED.username,
                full_name        = EXCLUDED.full_name,
                is_active        = EXCLUDED.is_active,
                tenant_id        = EXCLUDED.tenant_id,
                timezone         = EXCLUDED.timezone,
                is_delete        = EXCLUDED.is_delete,
                is_tenant_active = EXCLUDED.is_tenant_active
            """,
            {
                "user_id": new_user_id,
                "email": admin_email,
                "username": "admin",
                "full_name": "Default Admin",
                "is_active": True,
                "tenant_id": tenant_id,
                "timezone": "UTC",
                "is_delete": False,
                "is_tenant_active": True,
                "creation_type": "default",
                "created_by": SEEDER_ID,
            },
        )

        # Fetch the actual id (may differ from new_user_id on conflict)
        row = adapter.fetch_one(
            "SELECT id FROM users WHERE email = :email",
            {"email": admin_email},
        )
        actual_user_id = str(row[0])

        # Upsert credentials (unique on user_id FK)
        adapter.execute(
            """
            INSERT INTO user_credentials (user_id, password_hash, password_salt, created_by)
            VALUES (:user_id, :password_hash, :password_salt, :created_by)
            ON CONFLICT (user_id) DO UPDATE
            SET
                password_hash = EXCLUDED.password_hash,
                password_salt = EXCLUDED.password_salt
            """,
            {
                "user_id": actual_user_id,
                "password_hash": password_hash,
                "password_salt": salt,
                "created_by": SEEDER_ID,
            },
        )
        tenant_info = f" → tenant '{tenant_org}'" if tenant_id else " (no default tenant found)"
        print(f"    ✓ Created/updated default admin user (admin@ai4inclusion.org){tenant_info}")

        # Assign ADMIN role (user_role has no unique constraint on (user_id, role_id))
        adapter.execute(
            f"""
            INSERT INTO user_role (user_id, role_id, created_by)
            SELECT u.id, r.id, '{SEEDER_ID}'
            FROM users u
            JOIN roles r ON r.name = 'ADMIN'
            WHERE u.email = :email
              AND NOT EXISTS (
                  SELECT 1 FROM user_role ur
                  WHERE ur.user_id = u.id AND ur.role_id = r.id
              )
            """,
            {"email": admin_email},
        )
        print("    ✓ Assigned ADMIN role to default admin user in ai4iplatform_auth")
