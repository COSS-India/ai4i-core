"""
Default Admin User Seeder
Creates the default system administrator account
"""
from infrastructure.migrations.core.base_seeder import BaseSeeder


class AuthDefaultAdminSeeder(BaseSeeder):
    """Create default admin user for auth_db"""
    
    def run(self, adapter):
        """Run seeder"""
        # Create default admin user
        # Password hash for "Admin@123" (bcrypt)
        adapter.execute(
            """
            INSERT INTO users (email, username, password_hash, is_active, is_verified)
            VALUES (:email, :username, :password_hash, :is_active, :is_verified)
            ON CONFLICT (email) DO UPDATE
            SET 
                username = EXCLUDED.username,
                password_hash = EXCLUDED.password_hash,
                is_active = EXCLUDED.is_active,
                is_verified = EXCLUDED.is_verified
            """,
            {
                'email': 'admin@ai4i.org',
                'username': 'admin',
                'password_hash': '$2b$12$4RQ5dBZcbuUGcmtMrySGxOv7Jj4h.v088MTrkTadx4kPfa.GrsaWW',
                'is_active': True,
                'is_verified': True
            }
        )
        print("    ✓ Created default admin user (admin@ai4i.org / Admin@123)")
        
        # Assign ADMIN role to the default admin user
        adapter.execute("""
            INSERT INTO user_roles (user_id, role_id)
            SELECT u.id, r.id
            FROM users u, roles r
            WHERE u.email = 'admin@ai4i.org' 
              AND u.username = 'admin' 
              AND r.name = 'ADMIN'
            ON CONFLICT (user_id, role_id) DO NOTHING
        """)
        print("    ✓ Assigned ADMIN role to default admin user")
