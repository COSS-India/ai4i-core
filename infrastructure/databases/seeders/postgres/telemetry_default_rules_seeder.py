from infrastructure.databases.core.base_seeder import BaseSeeder


class TelemetryDefaultRulesSeeder(BaseSeeder):
    """Seed default data enrichment rules for telemetry_db."""
    
    database = 'telemetry_db'  # Target database
    
    def run(self, adapter):
        """Run the seeder."""
        # Insert default data enrichment rules
        adapter.execute("""
            INSERT INTO data_enrichment_rules (rule_name, source_field, target_field, enrichment_type, configuration, is_active)
            VALUES
            (
                'Extract User ID from Trace',
                'trace_id',
                'user_id',
                'extraction',
                '{"pattern": "user-([a-f0-9-]+)", "group": 1}'::jsonb,
                true
            ),
            (
                'Classify Log Level',
                'log_level',
                'severity',
                'classification',
                '{"mapping": {"DEBUG": "low", "INFO": "low", "WARNING": "medium", "ERROR": "high", "CRITICAL": "critical"}}'::jsonb,
                true
            ),
            (
                'Extract Service Name',
                'log_message',
                'service_name',
                'extraction',
                '{"pattern": "\\\\[([A-Za-z-]+)\\\\]", "group": 1}'::jsonb,
                true
            ),
            (
                'Add Environment Tag',
                'metadata',
                'environment',
                'enrichment',
                '{"default": "production", "sources": ["kubernetes.namespace", "env.ENVIRONMENT"]}'::jsonb,
                true
            ),
            (
                'Correlate Request ID',
                'request_id',
                'correlation_id',
                'correlation',
                '{"join_field": "request_id", "ttl_seconds": 3600}'::jsonb,
                true
            )
            ON CONFLICT (rule_name) DO NOTHING;
        """)
        print("    ✓ Inserted 5 default data enrichment rules")
