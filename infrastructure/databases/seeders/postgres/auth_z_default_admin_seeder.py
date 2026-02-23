"""
Default Admin User Seeder
Creates the default system administrator account
"""
from infrastructure.databases.core.base_seeder import BaseSeeder


class AuthDefaultAdminSeeder(BaseSeeder):
    """Create default admin user for auth_db"""
    
    database = 'auth_db'  # Target database
    
    def run(self, adapter):
        """Run seeder"""
        # Create default admin user if it doesn't exist
        # Password hash for "Admin@123" (bcrypt)
        
        # Insert admin user if it doesn't exist, or update if it exists
        adapter.execute(
            """
            INSERT INTO users (email, username, password_hash, is_active, is_verified, is_superuser)
            VALUES (:email, :username, :password_hash, :is_active, :is_verified, :is_superuser)
            ON CONFLICT (email) DO UPDATE
            SET 
                username = EXCLUDED.username,
                password_hash = EXCLUDED.password_hash,
                is_active = EXCLUDED.is_active,
                is_verified = EXCLUDED.is_verified,
                is_superuser = EXCLUDED.is_superuser
            """,
            {
                'email': 'admin@ai4inclusion.org',
                'username': 'admin',
                'password_hash': '$2b$12$4RQ5dBZcbuUGcmtMrySGxOv7Jj4h.v088MTrkTadx4kPfa.GrsaWW',
                'is_active': True,
                'is_verified': True,
                'is_superuser': True
            }
        )
        print("    ✓ Created/updated default admin user (admin@ai4inclusion.org / Admin@123)")
        
        # Ensure is_superuser is set to true for admin@ai4inclusion.org (in case it was false)
        adapter.execute(
            """
            UPDATE users 
            SET is_superuser = true 
            WHERE email = 'admin@ai4inclusion.org' AND is_superuser = false
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