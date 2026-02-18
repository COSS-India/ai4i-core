from infrastructure.databases.core.base_migration import BaseMigration

class CreateMetricsIndexes(BaseMigration):
    """Create indexes for metrics tables in metrics_db."""

    def up(self, adapter):
        """Run the migration."""
        # Indexes for api_metrics
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_metrics_timestamp ON api_metrics(timestamp);
            CREATE INDEX IF NOT EXISTS idx_api_metrics_service_name ON api_metrics(service_name);
            CREATE INDEX IF NOT EXISTS idx_api_metrics_endpoint ON api_metrics(endpoint);
            CREATE INDEX IF NOT EXISTS idx_api_metrics_status_code ON api_metrics(status_code);
            CREATE INDEX IF NOT EXISTS idx_api_metrics_timestamp_service ON api_metrics(timestamp, service_name);
        """)
        print("    ✓ Created indexes for api_metrics")

        # Indexes for custom_metrics
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_custom_metrics_metric_name ON custom_metrics(metric_name);
            CREATE INDEX IF NOT EXISTS idx_custom_metrics_timestamp ON custom_metrics(timestamp);
            CREATE INDEX IF NOT EXISTS idx_custom_metrics_user_id ON custom_metrics(user_id);
            CREATE INDEX IF NOT EXISTS idx_custom_metrics_tenant_id ON custom_metrics(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_custom_metrics_metric_timestamp ON custom_metrics(metric_name, timestamp);
        """)
        print("    ✓ Created indexes for custom_metrics")

        # Indexes for metric_aggregations
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_metric_aggregations_metric_name ON metric_aggregations(metric_name);
            CREATE INDEX IF NOT EXISTS idx_metric_aggregations_aggregation_type ON metric_aggregations(aggregation_type);
            CREATE INDEX IF NOT EXISTS idx_metric_aggregations_start_time ON metric_aggregations(start_time);
            CREATE INDEX IF NOT EXISTS idx_metric_aggregations_metric_type_time ON metric_aggregations(metric_name, aggregation_type, start_time);
        """)
        print("    ✓ Created indexes for metric_aggregations")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP INDEX IF EXISTS idx_metric_aggregations_metric_type_time;
            DROP INDEX IF EXISTS idx_metric_aggregations_start_time;
            DROP INDEX IF EXISTS idx_metric_aggregations_aggregation_type;
            DROP INDEX IF EXISTS idx_metric_aggregations_metric_name;
            DROP INDEX IF EXISTS idx_custom_metrics_metric_timestamp;
            DROP INDEX IF EXISTS idx_custom_metrics_tenant_id;
            DROP INDEX IF EXISTS idx_custom_metrics_user_id;
            DROP INDEX IF EXISTS idx_custom_metrics_timestamp;
            DROP INDEX IF EXISTS idx_custom_metrics_metric_name;
            DROP INDEX IF EXISTS idx_api_metrics_timestamp_service;
            DROP INDEX IF EXISTS idx_api_metrics_status_code;
            DROP INDEX IF EXISTS idx_api_metrics_endpoint;
            DROP INDEX IF EXISTS idx_api_metrics_service_name;
            DROP INDEX IF EXISTS idx_api_metrics_timestamp;
        """)
        print("    ✓ Dropped metrics indexes")
