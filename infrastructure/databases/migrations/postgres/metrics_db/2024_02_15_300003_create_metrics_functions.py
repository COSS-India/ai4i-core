from infrastructure.databases.core.base_migration import BaseMigration

class CreateMetricsFunctions(BaseMigration):
    """Create utility functions for metrics management in metrics_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create function to automatically create monthly partitions
        adapter.execute("""
            CREATE OR REPLACE FUNCTION create_monthly_partition(table_name text, start_date date)
            RETURNS void AS $$
            DECLARE
                partition_name text;
                end_date date;
            BEGIN
                partition_name := table_name || '_y' || to_char(start_date, 'YYYY') || 'm' || to_char(start_date, 'MM');
                end_date := start_date + interval '1 month';
                
                EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                               partition_name, table_name, start_date, end_date);
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created create_monthly_partition function")

        # Create function to clean up old metrics data
        adapter.execute("""
            CREATE OR REPLACE FUNCTION cleanup_old_metrics(retention_days integer DEFAULT 90)
            RETURNS void AS $$
            BEGIN
                DELETE FROM api_metrics 
                WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
                
                DELETE FROM custom_metrics 
                WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
                
                DELETE FROM metric_aggregations 
                WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * (retention_days * 2);
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created cleanup_old_metrics function")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP FUNCTION IF EXISTS cleanup_old_metrics CASCADE;
            DROP FUNCTION IF EXISTS create_monthly_partition CASCADE;
        """)
        print("    ✓ Dropped metrics functions")
