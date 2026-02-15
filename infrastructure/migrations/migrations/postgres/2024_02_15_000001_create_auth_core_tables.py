"""
Create Auth Core Tables Migration
Creates users, roles, permissions, and junction tables for auth_db
"""
from infrastructure.migrations.core.base_migration import BaseMigration


class CreateAuthCoreTables(BaseMigration):
    """Create core authentication and authorization tables"""
    
    def up(self, adapter):
        """Run migration"""
        # Create users table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                is_active BOOLEAN DEFAULT true,
                is_verified BOOLEAN DEFAULT false,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created users table")
        
        # Create roles table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created roles table")
        
        # Create permissions table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS permissions (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                resource VARCHAR(100) NOT NULL,
                action VARCHAR(50) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created permissions table")
        
        # Create user_roles junction table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
                assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, role_id)
            )
        """)
        print("    ✓ Created user_roles table")
        
        # Create role_permissions junction table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
                permission_id INTEGER REFERENCES permissions(id) ON DELETE CASCADE,
                assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (role_id, permission_id)
            )
        """)
        print("    ✓ Created role_permissions table")
        
        # Create indexes
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles(role_id)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id ON role_permissions(role_id)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_role_permissions_permission_id ON role_permissions(permission_id)")
        print("    ✓ Created indexes")
        
        # Create updated_at trigger function
        adapter.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql'
        """)
        
        # Create trigger for users
        adapter.execute("""
            CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)
        print("    ✓ Created triggers")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.execute("DROP TABLE IF EXISTS role_permissions CASCADE")
        adapter.execute("DROP TABLE IF EXISTS user_roles CASCADE")
        adapter.execute("DROP TABLE IF EXISTS permissions CASCADE")
        adapter.execute("DROP TABLE IF EXISTS roles CASCADE")
        adapter.execute("DROP TABLE IF EXISTS users CASCADE")
        adapter.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE")
        print("    ✓ Dropped all auth core tables")
