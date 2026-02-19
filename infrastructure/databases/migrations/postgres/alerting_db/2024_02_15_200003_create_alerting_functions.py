from infrastructure.databases.core.base_migration import BaseMigration

class CreateAlertingFunctions(BaseMigration):
    """Create functions and triggers for alerting system in alerting_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create updated_at trigger function
        adapter.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        print("    ✓ Created update_updated_at_column function")

        # Create triggers for updated_at columns
        adapter.execute("""
            CREATE TRIGGER update_alert_rules_updated_at 
                BEFORE UPDATE ON alert_rules
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            CREATE TRIGGER update_escalation_policies_updated_at 
                BEFORE UPDATE ON escalation_policies
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
        print("    ✓ Created updated_at triggers")

        # Create resolve_alert function
        adapter.execute("""
            CREATE OR REPLACE FUNCTION resolve_alert(alert_id integer, resolved_by varchar(100))
            RETURNS void AS $$
            BEGIN
                UPDATE alerts 
                SET status = 'resolved',
                    resolved_at = CURRENT_TIMESTAMP
                WHERE id = alert_id AND status = 'firing';
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created resolve_alert function")

        # Create acknowledge_alert function
        adapter.execute("""
            CREATE OR REPLACE FUNCTION acknowledge_alert(alert_id integer, acknowledged_by varchar(100))
            RETURNS void AS $$
            BEGIN
                UPDATE alerts 
                SET status = 'acknowledged',
                    acknowledged_at = CURRENT_TIMESTAMP,
                    acknowledged_by = acknowledge_alert.acknowledged_by
                WHERE id = alert_id AND status = 'firing';
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created acknowledge_alert function")

        # Create cleanup_old_alert_data function
        adapter.execute("""
            CREATE OR REPLACE FUNCTION cleanup_old_alert_data(retention_days integer DEFAULT 90)
            RETURNS void AS $$
            BEGIN
                DELETE FROM alerts 
                WHERE status = 'resolved' 
                AND resolved_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
                
                DELETE FROM notification_history 
                WHERE sent_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created cleanup_old_alert_data function")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TRIGGER IF EXISTS update_escalation_policies_updated_at ON escalation_policies;
            DROP TRIGGER IF EXISTS update_alert_rules_updated_at ON alert_rules;
            DROP FUNCTION IF EXISTS cleanup_old_alert_data CASCADE;
            DROP FUNCTION IF EXISTS acknowledge_alert CASCADE;
            DROP FUNCTION IF EXISTS resolve_alert CASCADE;
            DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;
        """)
        print("    ✓ Dropped alerting functions and triggers")
