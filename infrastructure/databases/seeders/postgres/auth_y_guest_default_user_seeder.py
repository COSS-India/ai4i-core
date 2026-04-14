"""
Default Guest User Seeder (auth_db)

Creates/updates the default guest user and assigns the GUEST role.
GUEST role → permissions are owned only by auth_roles_permissions_seeder.py (run first via filename order).

Default guest email is guest@ai4inclusion.org (same idea as admin@ai4inclusion.org in the admin seeder doc).
Set GUEST_EMAIL when seeding if you need a different address; it must match auth-service GUEST_EMAIL in .env.
Password: GUEST_PASSWORD (same pattern as ADMIN_DEFAULT_PASSWORD).
Falls back to literal \"GUEST_PASSWORD\" if unset (change in production).

Runs after auth_roles_permissions_seeder.py and auth_tenant_admin_role_seeder.py (filename order).
"""
import os

from infrastructure.databases.core.base_seeder import BaseSeeder
from infrastructure.databases.seeders.postgres.auth_seeder_credentials import (
    resolve_password_hash_material,
)


GUEST_USERNAME = "guest"


class AuthGuestDefaultUserSeeder(BaseSeeder):
    """Seed default guest user for auth_db (GUEST permissions: auth_roles_permissions_seeder)."""

    database = "auth_db"

    def run(self, adapter):
        guest_email = (os.getenv("GUEST_EMAIL") or "guest@ai4inclusion.org").strip()
        password_plain = os.getenv("GUEST_PASSWORD", "GUEST_PASSWORD")

        password_hash, salt, hash_rounds = resolve_password_hash_material(
            password_plain, adapter, guest_email
        )

        adapter.execute(
            """
            INSERT INTO users (
                email, username, password_hash, password_salt, hash_rounds,
                is_active, is_verified, is_superuser, timezone, language
            )
            VALUES (
                :email, :username, :password_hash, :password_salt, :hash_rounds,
                :is_active, :is_verified, :is_superuser, :timezone, :language
            )
            ON CONFLICT (email) DO UPDATE
            SET
                username = EXCLUDED.username,
                password_hash = EXCLUDED.password_hash,
                password_salt = EXCLUDED.password_salt,
                hash_rounds = EXCLUDED.hash_rounds,
                is_active = EXCLUDED.is_active,
                is_verified = EXCLUDED.is_verified,
                is_superuser = EXCLUDED.is_superuser,
                timezone = EXCLUDED.timezone,
                language = EXCLUDED.language
            """,
            {
                "email": guest_email,
                "username": GUEST_USERNAME,
                "password_hash": password_hash,
                "password_salt": salt,
                "hash_rounds": hash_rounds,
                "is_active": True,
                "is_verified": True,
                "is_superuser": False,
                "timezone": "UTC",
                "language": "en",
            },
        )
        print(f"    ✓ Created/updated default guest user ({guest_email})")

        adapter.execute(
            """
            INSERT INTO user_roles (user_id, role_id)
            SELECT u.id, r.id
            FROM users u, roles r
            WHERE u.email = :email
              AND u.username = :username
              AND r.name = 'GUEST'
            ON CONFLICT (user_id, role_id) DO NOTHING
            """,
            {"email": guest_email, "username": GUEST_USERNAME},
        )
        print("    ✓ Assigned GUEST role to default guest user")
