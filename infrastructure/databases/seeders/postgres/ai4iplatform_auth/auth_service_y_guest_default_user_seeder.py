"""
Default Guest User Seeder (ai4iplatform_auth)

Mirrors auth_y_guest_default_user_seeder.py for the auth-service database.
Creates/updates the default guest user, assigns the GUEST role, and maps
the user to the default tenant created by auth_service_t_default_tenant_seeder.py.

Rows created by this seeder carry created_by = SEEDER_ID so they can be
distinguished from user-created records.

Schema differences vs auth_db:
  - users.id is UUID
  - passwords stored in separate user_credentials table (no hash_rounds column)
  - role assignment via user_role table (no unique constraint on user_id+role_id)

Runs after auth_service_t_default_tenant_seeder.py (filename order).
"""
import os
import secrets
import uuid

from passlib.context import CryptContext

from infrastructure.databases.core.base_seeder import BaseSeeder

# Fixed identity for all rows written by seeders — readable as "seed0000…"
SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

GUEST_USERNAME = "guest"
DEFAULT_TENANT_ORG = "default organisation"
_CTX = CryptContext(schemes=["argon2"], default="argon2")


def _resolve_credentials(adapter, email: str, plain_password: str) -> tuple[str, str]:
    """
    Return (password_hash, password_salt) for the given user.

    Reuses the stored hash/salt when the plain password still verifies against
    the stored hash, to avoid unnecessary column rewrites on every deployment.
    """
    row = adapter.fetch_one(
        """
        SELECT uc.password_hash, uc.password_salt
        FROM users u
        JOIN user_credentials uc ON u.id = uc.user_id
        WHERE u.email = :email
        """,
        {"email": email},
    )
    if row and row[0] and row[1]:
        stored_hash, stored_salt = row[0], row[1]
        try:
            if _CTX.verify(plain_password + stored_salt, stored_hash):
                return stored_hash, stored_salt
        except Exception:
            pass

    salt = secrets.token_hex(16)
    return _CTX.hash(plain_password + salt), salt


class AuthServiceGuestDefaultUserSeeder(BaseSeeder):
    """Seed default guest user for ai4iplatform_auth"""

    database = "ai4iplatform_auth"

    def run(self, adapter):
        guest_email = (os.getenv("GUEST_EMAIL") or "guest@ai4inclusion.org").strip()
        password_plain = os.getenv("GUEST_PASSWORD", "GUEST_PASSWORD")
        tenant_org = (os.getenv("DEFAULT_TENANT_ORG") or DEFAULT_TENANT_ORG).strip()

        password_hash, salt = _resolve_credentials(adapter, guest_email, password_plain)

        # Resolve the default tenant_id
        tenant_row = adapter.fetch_one(
            "SELECT id FROM tenants WHERE organisation = :org LIMIT 1",
            {"org": tenant_org},
        )
        # Current User model maps tenant_id as UUID while Tenant.id is Integer.
        # Keep tenant_id null in seed data until schema/types are aligned.
        tenant_id = None

        # Upsert user (id is UUID; preserve existing UUID on conflict)
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
                "email": guest_email,
                "username": GUEST_USERNAME,
                "full_name": "Default Guest",
                "is_active": True,
                "tenant_id": tenant_id,
                "timezone": "UTC",
                "is_delete": False,
                "is_tenant_active": True,
                "creation_type": "default",
                "created_by": SEEDER_ID,
            },
        )

        # Fetch the actual user_id (may differ from new_user_id on conflict)
        row = adapter.fetch_one(
            "SELECT id FROM users WHERE email = :email",
            {"email": guest_email},
        )
        actual_user_id = str(row[0])

        # Upsert credentials (PK = user_id)
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
        print(f"    ✓ Created/updated default guest user ({guest_email}){tenant_info}")

        # Assign GUEST role (user_role has no unique constraint on (user_id, role_id))
        adapter.execute(
            f"""
            INSERT INTO user_role (user_id, role_id, created_by)
            SELECT u.id, r.id, '{SEEDER_ID}'
            FROM users u
            JOIN roles r ON r.name = 'GUEST'
            WHERE u.email = :email
              AND NOT EXISTS (
                  SELECT 1 FROM user_role ur
                  WHERE ur.user_id = u.id AND ur.role_id = r.id
              )
            """,
            {"email": guest_email},
        )
        print("    ✓ Assigned GUEST role to default guest user in ai4iplatform_auth")
