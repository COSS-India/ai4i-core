"""
Default Admin User Seeder
Creates the default system administrator account.

IMPORTANT: After first login, change the default admin password immediately.
The default password is set via ADMIN_DEFAULT_PASSWORD env var (falls back to 'ADMIN_PASSWORD').
"""
import os

from infrastructure.databases.core.base_seeder import BaseSeeder
from infrastructure.databases.seeders.postgres.auth_seeder_credentials import (
    resolve_password_hash_material,
)


class AuthDefaultAdminSeeder(BaseSeeder):
    """Create default admin user for auth_db"""

    database = 'auth_db'  # Target database

    def run(self, adapter):
        """Run seeder"""
        default_password = os.getenv("ADMIN_DEFAULT_PASSWORD", "ADMIN_PASSWORD")
        admin_email = "admin@ai4inclusion.org"
        password_hash, salt, hash_rounds = resolve_password_hash_material(
            default_password, adapter, admin_email
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
                'email': admin_email,
                'username': 'admin',
                'password_hash': password_hash,
                'password_salt': salt,
                'hash_rounds': hash_rounds,
                'is_active': True,
                'is_verified': True,
                'is_superuser': True,
                'timezone': 'UTC',
                'language': 'en',
            }
        )
        print("    ✓ Created/updated default admin user (admin@ai4inclusion.org)")
        
        # Ensure is_superuser is set to true for admin@ai4inclusion.org (in case it was false)
        adapter.execute(
            """
            UPDATE users 
            SET is_superuser = true,
                timezone = COALESCE(timezone, 'UTC'),
                language = COALESCE(language, 'en')
            WHERE email = 'admin@ai4inclusion.org'
            """
        )
        
        # Assign ADMIN role to the default admin user
        adapter.execute("""
            INSERT INTO user_roles (user_id, role_id)
            SELECT u.id, r.id
            FROM users u, roles r
            WHERE u.email = 'admin@ai4inclusion.org' 
              AND u.username = 'admin' 
              AND r.name = 'ADMIN'
            ON CONFLICT (user_id, role_id) DO NOTHING
        """)
        print("    ✓ Assigned ADMIN role to default admin user")
        
        # Ensure ADMIN role has ALL permissions (including any that might have been added)
        # This ensures the admin user always has full access
        adapter.execute("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.name = 'ADMIN'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        """)
        print("    ✓ Ensured ADMIN role has all permissions")