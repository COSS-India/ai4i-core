from infrastructure.databases.core.base_migration import BaseMigration

class CreateTelemetryIndexes(BaseMigration):
    """Create indexes for telemetry tables in telemetry_db."""

    def up(self, adapter):
        """Run the migration."""
        # Indexes for log_metadata
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_log_metadata_log_id ON log_metadata(log_id);
            CREATE INDEX IF NOT EXISTS idx_log_metadata_service_name ON log_metadata(service_name);
            CREATE INDEX IF NOT EXISTS idx_log_metadata_correlation_id ON log_metadata(correlation_id);
            CREATE INDEX IF NOT EXISTS idx_log_metadata_created_at ON log_metadata(created_at);
            CREATE INDEX IF NOT EXISTS idx_log_metadata_service_correlation ON log_metadata(service_name, correlation_id);
        """)
        print("    ✓ Created indexes for log_metadata")

        # Indexes for trace_metadata
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_trace_metadata_trace_id ON trace_metadata(trace_id);
            CREATE INDEX IF NOT EXISTS idx_trace_metadata_span_id ON trace_metadata(span_id);
            CREATE INDEX IF NOT EXISTS idx_trace_metadata_parent_span_id ON trace_metadata(parent_span_id);
            CREATE INDEX IF NOT EXISTS idx_trace_metadata_service_name ON trace_metadata(service_name);
            CREATE INDEX IF NOT EXISTS idx_trace_metadata_created_at ON trace_metadata(created_at);
            CREATE INDEX IF NOT EXISTS idx_trace_metadata_trace_span ON trace_metadata(trace_id, span_id);
        """)
        print("    ✓ Created indexes for trace_metadata")

        # Indexes for event_correlations
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_correlations_correlation_id ON event_correlations(correlation_id);
            CREATE INDEX IF NOT EXISTS idx_event_correlations_event_type ON event_correlations(event_type);
            CREATE INDEX IF NOT EXISTS idx_event_correlations_first_seen ON event_correlations(first_seen);
            CREATE INDEX IF NOT EXISTS idx_event_correlations_last_seen ON event_correlations(last_seen);
        """)
        print("    ✓ Created indexes for event_correlations")

        # Indexes for data_enrichment_rules
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_data_enrichment_rules_rule_name ON data_enrichment_rules(rule_name);
            CREATE INDEX IF NOT EXISTS idx_data_enrichment_rules_active ON data_enrichment_rules(is_active);
        """)
        print("    ✓ Created indexes for data_enrichment_rules")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP INDEX IF EXISTS idx_data_enrichment_rules_active;
            DROP INDEX IF EXISTS idx_data_enrichment_rules_rule_name;
            DROP INDEX IF EXISTS idx_event_correlations_last_seen;
            DROP INDEX IF EXISTS idx_event_correlations_first_seen;
            DROP INDEX IF EXISTS idx_event_correlations_event_type;
            DROP INDEX IF EXISTS idx_event_correlations_correlation_id;
            DROP INDEX IF EXISTS idx_trace_metadata_trace_span;
            DROP INDEX IF EXISTS idx_trace_metadata_created_at;
            DROP INDEX IF EXISTS idx_trace_metadata_service_name;
            DROP INDEX IF EXISTS idx_trace_metadata_parent_span_id;
            DROP INDEX IF EXISTS idx_trace_metadata_span_id;
            DROP INDEX IF EXISTS idx_trace_metadata_trace_id;
            DROP INDEX IF EXISTS idx_log_metadata_service_correlation;
            DROP INDEX IF EXISTS idx_log_metadata_created_at;
            DROP INDEX IF EXISTS idx_log_metadata_correlation_id;
            DROP INDEX IF EXISTS idx_log_metadata_service_name;
            DROP INDEX IF EXISTS idx_log_metadata_log_id;
        """)
        print("    ✓ Dropped telemetry indexes")
