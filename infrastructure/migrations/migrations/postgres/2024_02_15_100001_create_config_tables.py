"""
Create Config Tables Migration
Creates configurations, feature_flags, and service_registry tables for config_db
Note: Use --postgres-db config_db when running this migration
"""
from infrastructure.migrations.core.base_migration import BaseMigration


class CreateConfigTables(BaseMigration):
    """Create configuration management tables"""
    
    def up(self, adapter):
        """Run migration"""
        # Create configurations table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS configurations (
                id SERIAL PRIMARY KEY,
                key VARCHAR(255) NOT NULL,
                value TEXT NOT NULL,
                environment VARCHAR(50) NOT NULL,
                service_name VARCHAR(100) NOT NULL,
                is_encrypted BOOLEAN DEFAULT false,
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(key, environment, service_name)
            )
        """)
        print("    ✓ Created configurations table")
        
        # Create feature_flags table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS feature_flags (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                is_enabled BOOLEAN DEFAULT false,
                rollout_percentage VARCHAR(255),
                target_users JSONB,
                environment VARCHAR(50) NOT NULL,
                unleash_flag_name VARCHAR(255),
                last_synced_at TIMESTAMP WITH TIME ZONE,
                evaluation_count INTEGER DEFAULT 0,
                last_evaluated_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (name, environment)
            )
        """)
        print("    ✓ Created feature_flags table")
        
        # Create service_registry table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS service_registry (
                id SERIAL PRIMARY KEY,
                service_name VARCHAR(100) UNIQUE NOT NULL,
                service_url VARCHAR(255) NOT NULL,
                health_check_url VARCHAR(255),
                status VARCHAR(20) DEFAULT 'unknown',
                last_health_check TIMESTAMP WITH TIME ZONE,
                service_metadata JSONB,
                registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created service_registry table")
        
        # Create configuration_history table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS configuration_history (
                id SERIAL PRIMARY KEY,
                configuration_id INTEGER REFERENCES configurations(id) ON DELETE CASCADE,
                old_value TEXT,
                new_value TEXT,
                changed_by VARCHAR(100),
                changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created configuration_history table")
        
        # Create feature_flag_evaluations table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS feature_flag_evaluations (
                id SERIAL PRIMARY KEY,
                flag_name VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                context JSONB,
                result BOOLEAN,
                variant VARCHAR(100),
                evaluated_value JSONB,
                environment VARCHAR(50) NOT NULL,
                evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                evaluation_reason VARCHAR(50)
            )
        """)
        print("    ✓ Created feature_flag_evaluations table")
        
        # Create indexes
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_configurations_key ON configurations(key)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_configurations_environment ON configurations(environment)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_configurations_service_name ON configurations(service_name)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_feature_flags_name ON feature_flags(name)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_feature_flags_environment ON feature_flags(environment)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_feature_flags_enabled ON feature_flags(is_enabled)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_service_registry_service_name ON service_registry(service_name)")
        adapter.execute("CREATE INDEX IF NOT EXISTS idx_service_registry_status ON service_registry(status)")
        print("    ✓ Created indexes")
        
        # Create updated_at trigger function if not exists
        adapter.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql'
        """)
        
        # Create triggers
        adapter.execute("""
            CREATE TRIGGER update_configurations_updated_at BEFORE UPDATE ON configurations
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)
        adapter.execute("""
            CREATE TRIGGER update_feature_flags_updated_at BEFORE UPDATE ON feature_flags
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)
        adapter.execute("""
            CREATE TRIGGER update_service_registry_updated_at BEFORE UPDATE ON service_registry
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)
        print("    ✓ Created triggers")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.execute("DROP TABLE IF EXISTS feature_flag_evaluations CASCADE")
        adapter.execute("DROP TABLE IF EXISTS configuration_history CASCADE")
        adapter.execute("DROP TABLE IF EXISTS service_registry CASCADE")
        adapter.execute("DROP TABLE IF EXISTS feature_flags CASCADE")
        adapter.execute("DROP TABLE IF EXISTS configurations CASCADE")
        adapter.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE")
        print("    ✓ Dropped all config tables")
