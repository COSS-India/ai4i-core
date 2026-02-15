"""
Create API Keys and Sessions Tables Migration
Creates api_keys and sessions tables for auth_db
"""
from infrastructure.migrations.core.base_migration import BaseMigration


class CreateApiKeysSessionsTables(BaseMigration):
    """Create API keys and sessions tables"""
    
    def up(self, adapter):
        """Run migration"""
        # Create api_keys table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                key_hash VARCHAR(255) UNIQUE NOT NULL,
                key_name VARCHAR(100) NOT NULL,
                key_value_encrypted TEXT,
                permissions JSONB DEFAULT '[]'::jsonb,
                is_active BOOLEAN DEFAULT true,
                expires_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP WITH TIME ZONE
            )
        """)
        print("    ✓ Created api_keys table")
        
        # Create sessions table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                session_token VARCHAR(255) UNIQUE NOT NULL,
                ip_address INET,
                user_agent TEXT,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created sessions table")
        
        # Create indexes
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
        print("    ✓ Created indexes")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.execute("DROP TABLE IF EXISTS sessions CASCADE")
        adapter.execute("DROP TABLE IF EXISTS api_keys CASCADE")
        print("    ✓ Dropped api_keys and sessions tables")
