from infrastructure.databases.core.base_migration import BaseMigration

class CreateTelemetryTables(BaseMigration):
    """Create telemetry tables (log_metadata, trace_metadata, event_correlations, data_enrichment_rules) in telemetry_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create log_metadata table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS log_metadata (
                id SERIAL PRIMARY KEY,
                log_id VARCHAR(255) UNIQUE NOT NULL,
                service_name VARCHAR(100) NOT NULL,
                environment VARCHAR(50) NOT NULL,
                log_level VARCHAR(20) NOT NULL,
                correlation_id VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created log_metadata table")

        # Create trace_metadata table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS trace_metadata (
                id SERIAL PRIMARY KEY,
                trace_id VARCHAR(255) NOT NULL,
                span_id VARCHAR(255) NOT NULL,
                parent_span_id VARCHAR(255),
                service_name VARCHAR(100) NOT NULL,
                operation_name VARCHAR(255) NOT NULL,
                duration DECIMAL(10,3) NOT NULL,
                status VARCHAR(20) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created trace_metadata table")

        # Create event_correlations table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS event_correlations (
                id SERIAL PRIMARY KEY,
                correlation_id VARCHAR(255) NOT NULL,
                event_type VARCHAR(100) NOT NULL,
                event_count INTEGER DEFAULT 1,
                first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created event_correlations table")

        # Create data_enrichment_rules table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS data_enrichment_rules (
                id SERIAL PRIMARY KEY,
                rule_name VARCHAR(255) UNIQUE NOT NULL,
                source_field VARCHAR(255) NOT NULL,
                target_field VARCHAR(255) NOT NULL,
                enrichment_type VARCHAR(50) NOT NULL,
                configuration JSONB NOT NULL,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created data_enrichment_rules table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS data_enrichment_rules CASCADE;
            DROP TABLE IF EXISTS event_correlations CASCADE;
            DROP TABLE IF EXISTS trace_metadata CASCADE;
            DROP TABLE IF EXISTS log_metadata CASCADE;
        """)
        print("    ✓ Dropped telemetry tables")
