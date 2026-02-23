from infrastructure.databases.core.base_migration import BaseMigration

class CreateAlertingBasicIndexes(BaseMigration):
    """Create indexes for basic alerting tables in alerting_db."""

    def up(self, adapter):
        """Run the migration."""
        # Indexes for alert_rules
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_rules_name ON alert_rules(name);
            CREATE INDEX IF NOT EXISTS idx_alert_rules_metric_name ON alert_rules(metric_name);
            CREATE INDEX IF NOT EXISTS idx_alert_rules_active ON alert_rules(is_active);
        """)
        print("    ✓ Created indexes for alert_rules")

        # Indexes for alerts
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_rule_id ON alerts(rule_id);
            CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
            CREATE INDEX IF NOT EXISTS idx_alerts_fired_at ON alerts(fired_at);
            CREATE INDEX IF NOT EXISTS idx_alerts_metric_name ON alerts(metric_name);
            CREATE INDEX IF NOT EXISTS idx_alerts_rule_status ON alerts(rule_id, status);
        """)
        print("    ✓ Created indexes for alerts")

        # Indexes for notification_history
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_notification_history_alert_id ON notification_history(alert_id);
            CREATE INDEX IF NOT EXISTS idx_notification_history_sent_at ON notification_history(sent_at);
            CREATE INDEX IF NOT EXISTS idx_notification_history_status ON notification_history(status);
        """)
        print("    ✓ Created indexes for notification_history")

        # Indexes for escalation_policies
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_escalation_policies_name ON escalation_policies(name);
        """)
        print("    ✓ Created indexes for escalation_policies")

        # Indexes for anomaly_detection_models
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_anomaly_models_metric_name ON anomaly_detection_models(metric_name);
            CREATE INDEX IF NOT EXISTS idx_anomaly_models_active ON anomaly_detection_models(is_active);
            CREATE INDEX IF NOT EXISTS idx_anomaly_models_last_trained ON anomaly_detection_models(last_trained_at);
        """)
        print("    ✓ Created indexes for anomaly_detection_models")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP INDEX IF EXISTS idx_anomaly_models_last_trained;
            DROP INDEX IF EXISTS idx_anomaly_models_active;
            DROP INDEX IF EXISTS idx_anomaly_models_metric_name;
            DROP INDEX IF EXISTS idx_escalation_policies_name;
            DROP INDEX IF EXISTS idx_notification_history_status;
            DROP INDEX IF EXISTS idx_notification_history_sent_at;
            DROP INDEX IF EXISTS idx_notification_history_alert_id;
            DROP INDEX IF EXISTS idx_alerts_rule_status;
            DROP INDEX IF EXISTS idx_alerts_metric_name;
            DROP INDEX IF EXISTS idx_alerts_fired_at;
            DROP INDEX IF EXISTS idx_alerts_status;
            DROP INDEX IF EXISTS idx_alerts_rule_id;
            DROP INDEX IF EXISTS idx_alert_rules_active;
            DROP INDEX IF EXISTS idx_alert_rules_metric_name;
            DROP INDEX IF EXISTS idx_alert_rules_name;
        """)
        print("    ✓ Dropped alerting indexes")
