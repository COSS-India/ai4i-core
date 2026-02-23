from infrastructure.databases.core.base_migration import BaseMigration

class CreateMetricsTables(BaseMigration):
    """Create metrics tables (metric_definitions, api_metrics, custom_metrics, metric_aggregations) in metrics_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create metric_definitions table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS metric_definitions (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                description TEXT,
                unit VARCHAR(50),
                metric_type VARCHAR(50) NOT NULL,
                aggregation_method VARCHAR(50),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created metric_definitions table")

        # Create api_metrics table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS api_metrics (
                id SERIAL PRIMARY KEY,
                endpoint VARCHAR(255) NOT NULL,
                method VARCHAR(10) NOT NULL,
                status_code INTEGER NOT NULL,
                response_time DECIMAL(10,3) NOT NULL,
                request_count INTEGER DEFAULT 1,
                error_count INTEGER DEFAULT 0,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                service_name VARCHAR(100) NOT NULL
            );
        """)
        print("    ✓ Created api_metrics table")

        # Create custom_metrics table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS custom_metrics (
                id SERIAL PRIMARY KEY,
                metric_name VARCHAR(255) NOT NULL,
                value DECIMAL(15,6) NOT NULL,
                tags JSONB,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                tenant_id VARCHAR(100)
            );
        """)
        print("    ✓ Created custom_metrics table")

        # Create metric_aggregations table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS metric_aggregations (
                id SERIAL PRIMARY KEY,
                metric_name VARCHAR(255) NOT NULL,
                aggregation_type VARCHAR(50) NOT NULL,
                value DECIMAL(15,6) NOT NULL,
                start_time TIMESTAMP WITH TIME ZONE NOT NULL,
                end_time TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created metric_aggregations table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS metric_aggregations CASCADE;
            DROP TABLE IF EXISTS custom_metrics CASCADE;
            DROP TABLE IF EXISTS api_metrics CASCADE;
            DROP TABLE IF EXISTS metric_definitions CASCADE;
        """)
        print("    ✓ Dropped metrics tables")
