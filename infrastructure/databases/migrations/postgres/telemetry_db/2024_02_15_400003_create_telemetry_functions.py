from infrastructure.databases.core.base_migration import BaseMigration

class CreateTelemetryFunctions(BaseMigration):
    """Create functions and triggers for telemetry management in telemetry_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create function to update event correlation timestamp
        adapter.execute("""
            CREATE OR REPLACE FUNCTION update_event_correlation_timestamp()
            RETURNS TRIGGER AS $$
            BEGIN
                IF EXISTS (SELECT 1 FROM event_correlations WHERE correlation_id = NEW.correlation_id) THEN
                    UPDATE event_correlations 
                    SET event_count = event_count + 1,
                        last_seen = CURRENT_TIMESTAMP
                    WHERE correlation_id = NEW.correlation_id;
                    RETURN NULL;
                ELSE
                    RETURN NEW;
                END IF;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created update_event_correlation_timestamp function")

        # Create trigger for event correlations
        adapter.execute("""
            CREATE TRIGGER update_event_correlation_timestamp_trigger
                BEFORE INSERT ON event_correlations
                FOR EACH ROW EXECUTE FUNCTION update_event_correlation_timestamp();
        """)
        print("    ✓ Created trigger for event correlations")

        # Create function to clean up old telemetry data
        adapter.execute("""
            CREATE OR REPLACE FUNCTION cleanup_old_telemetry_data(
                log_retention_days integer DEFAULT 30,
                trace_retention_days integer DEFAULT 7
            )
            RETURNS void AS $$
            BEGIN
                DELETE FROM log_metadata 
                WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * log_retention_days;
                
                DELETE FROM trace_metadata 
                WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * trace_retention_days;
                
                DELETE FROM event_correlations 
                WHERE last_seen < CURRENT_TIMESTAMP - INTERVAL '1 day' * log_retention_days;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created cleanup_old_telemetry_data function")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP FUNCTION IF EXISTS cleanup_old_telemetry_data CASCADE;
            DROP TRIGGER IF EXISTS update_event_correlation_timestamp_trigger ON event_correlations;
            DROP FUNCTION IF EXISTS update_event_correlation_timestamp CASCADE;
        """)
        print("    ✓ Dropped telemetry functions and triggers")
