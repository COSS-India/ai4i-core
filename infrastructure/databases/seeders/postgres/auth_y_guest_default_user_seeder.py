"""
Default Guest User Seeder (auth_db)

1. Maps the GUEST role to users.read (for GET /api/v1/auth/me) plus asr/nmt/tts inference (idempotent).
2. Creates/updates default guest user (email from GUEST_EMAIL) and assigns GUEST role.

Email: set GUEST_EMAIL in the environment (must match auth-service guest login).
Password: set GUEST_PASSWORD in the environment (same pattern as ADMIN_DEFAULT_PASSWORD).
Falls back to literal \"GUEST_PASSWORD\" if unset (change in production).

Runs after auth_roles_permissions_seeder.py and auth_tenant_admin_role_seeder.py (filename order).
"""
import os
import secrets

from passlib.context import CryptContext

from infrastructure.databases.core.base_seeder import BaseSeeder


GUEST_USERNAME = "guest"


class AuthGuestDefaultUserSeeder(BaseSeeder):
    """Seed GUEST role permissions + default guest user for auth_db."""

    database = "auth_db"

    def run(self, adapter):
        # Keep GUEST role aligned with inference-only access (idempotent if roles seeder ran first).
        adapter.execute(
            """
            DELETE FROM role_permissions
            WHERE role_id IN (SELECT id FROM roles WHERE name = 'GUEST');
            """
        )
        adapter.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.read',
              'asr.inference',
              'nmt.inference',
              'tts.inference'
            )
            WHERE r.name = 'GUEST'
            ON CONFLICT (role_id, permission_id) DO NOTHING;
            """
        )
        print(
            "    ✓ GUEST role → users.read, asr.inference, nmt.inference, tts.inference"
        )

        guest_email = (os.environ.get("GUEST_EMAIL") or "").strip()
        if not guest_email:
            print("    ⚠ GUEST_EMAIL not set; skipping default guest user seed")
            return

        password_plain = os.getenv("GUEST_PASSWORD", "GUEST_PASSWORD")
        salt = secrets.token_hex(16)
        password_hash = CryptContext(schemes=["argon2"], default="argon2").hash(
            password_plain + salt
        )
        hash_rounds = 12

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
