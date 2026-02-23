from infrastructure.databases.core.base_migration import BaseMigration


class CreateUserSessionsTable(BaseMigration):
    """Create user_sessions table in auth_db with enhanced session tracking."""

    def up(self, adapter):
        """Run the migration."""
        adapter.execute("""
            -- Create sequence for user_sessions if it doesn't exist
            CREATE SEQUENCE IF NOT EXISTS sessions_id_seq;

            -- User sessions table (enhanced session tracking)
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER DEFAULT nextval('sessions_id_seq') NOT NULL,
                user_id INTEGER,
                session_token TEXT NOT NULL,
                ip_address VARCHAR(45),
                user_agent TEXT,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                refresh_token TEXT,
                device_info JSONB,
                is_active BOOLEAN DEFAULT true,
                last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                token_type VARCHAR(20) DEFAULT 'access',
                CONSTRAINT user_sessions_pkey PRIMARY KEY (id),
                CONSTRAINT user_sessions_session_token_key UNIQUE (session_token),
                CONSTRAINT user_sessions_refresh_token_key UNIQUE (refresh_token),
                CONSTRAINT user_sessions_user_id_fkey 
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- Create indexes for user_sessions
            CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_sessions_session_token ON user_sessions(session_token);
            CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_token ON user_sessions(refresh_token);
            CREATE INDEX IF NOT EXISTS idx_user_sessions_is_active ON user_sessions(is_active);
            CREATE INDEX IF NOT EXISTS idx_user_sessions_token_type ON user_sessions(token_type);
        """)
        print("    ✓ Created user_sessions table with enhanced tracking")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS user_sessions CASCADE;
            DROP SEQUENCE IF EXISTS sessions_id_seq CASCADE;
        """)
        print("    ✓ Dropped user_sessions table")
