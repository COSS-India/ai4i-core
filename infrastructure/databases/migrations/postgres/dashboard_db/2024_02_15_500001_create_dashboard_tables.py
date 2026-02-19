from infrastructure.databases.core.base_migration import BaseMigration

class CreateDashboardTables(BaseMigration):
    """Create dashboard tables (dashboards, dashboard_widgets, saved_queries, reports, user_preferences) in dashboard_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create dashboards table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS dashboards (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                layout JSONB NOT NULL,
                is_public BOOLEAN DEFAULT false,
                owner_id INTEGER NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created dashboards table")

        # Create dashboard_widgets table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_widgets (
                id SERIAL PRIMARY KEY,
                dashboard_id INTEGER REFERENCES dashboards(id) ON DELETE CASCADE,
                widget_type VARCHAR(100) NOT NULL,
                configuration JSONB NOT NULL,
                position JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created dashboard_widgets table")

        # Create saved_queries table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS saved_queries (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                query TEXT NOT NULL,
                parameters JSONB,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created saved_queries table")

        # Create reports table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                schedule VARCHAR(100),
                recipients TEXT[],
                format VARCHAR(20) DEFAULT 'pdf',
                query_id INTEGER REFERENCES saved_queries(id) ON DELETE SET NULL,
                last_generated_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created reports table")

        # Create user_preferences table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                preferences JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created user_preferences table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS user_preferences CASCADE;
            DROP TABLE IF EXISTS reports CASCADE;
            DROP TABLE IF EXISTS saved_queries CASCADE;
            DROP TABLE IF EXISTS dashboard_widgets CASCADE;
            DROP TABLE IF EXISTS dashboards CASCADE;
        """)
        print("    ✓ Dropped dashboard tables")
