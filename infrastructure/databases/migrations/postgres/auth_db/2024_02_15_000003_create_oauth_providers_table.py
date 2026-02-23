"""
Create OAuth Providers Table Migration
Creates oauth_providers table for auth_db
"""
from infrastructure.databases.core.base_migration import BaseMigration


class CreateOauthProvidersTable(BaseMigration):
    """Create OAuth providers table for social authentication"""
    
    def up(self, adapter):
        """Run migration"""
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS oauth_providers (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                provider_name VARCHAR(50) NOT NULL,
                provider_user_id VARCHAR(255) NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider_name, provider_user_id)
            )
        """)
        print("    ✓ Created oauth_providers table")
        
        # Create indexes
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_oauth_providers_user_id ON oauth_providers(user_id)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_oauth_providers_provider ON oauth_providers(provider_name, provider_user_id)")
        print("    ✓ Created indexes")
        
        # Create trigger
        adapter.execute("""
            CREATE TRIGGER update_oauth_providers_updated_at BEFORE UPDATE ON oauth_providers
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)
        print("    ✓ Created trigger")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.execute("DROP TABLE IF EXISTS oauth_providers CASCADE")
        print("    ✓ Dropped oauth_providers table")
