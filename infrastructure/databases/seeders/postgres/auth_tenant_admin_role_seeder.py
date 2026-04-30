"""
Tenant Admin Role Seeder
Seeds the TENANT ADMIN role into the roles table for auth_db
"""
from infrastructure.databases.core.base_seeder import BaseSeeder


class AuthTenantAdminRoleSeeder(BaseSeeder):
    """Seed TENANT ADMIN role for auth_db"""
    
    database = 'auth_db'  # Target database
    
    def run(self, adapter):
        """
        Run seeder - inserts TENANT ADMIN role if it doesn't exist.
        
        This seeder is IDEMPOTENT - safe to run multiple times:
        - Uses ON CONFLICT to prevent duplicate inserts
        - Updates description if role already exists with different description
        """
        # Insert TENANT ADMIN role if it doesn't exist, or update description if it exists
        adapter.execute(
            """
            INSERT INTO roles (name, description)
            VALUES (:name, :description)
            ON CONFLICT (name) DO UPDATE
              SET description = EXCLUDED.description
            """,
            {
                'name': 'TENANT ADMIN',
                'description': 'Tenant administrator with permissions to manage tenant users and resources'
            }
        )
        print("    ✓ Seeded TENANT ADMIN role (idempotent - safe to run multiple times)")
