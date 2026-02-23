from infrastructure.databases.core.base_migration import BaseMigration

class CreateDynamicAlertIndexes(BaseMigration):
    """Create indexes for dynamic alert configuration tables in alerting_db."""

    def up(self, adapter):
        """Run the migration."""
        # Indexes for alert_definitions
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_definitions_organization ON alert_definitions(organization);
            CREATE INDEX IF NOT EXISTS idx_alert_definitions_enabled ON alert_definitions(enabled);
            CREATE INDEX IF NOT EXISTS idx_alert_definitions_category ON alert_definitions(category);
            CREATE INDEX IF NOT EXISTS idx_alert_definitions_severity ON alert_definitions(severity);
            CREATE INDEX IF NOT EXISTS idx_alert_definitions_organization_enabled ON alert_definitions(organization, enabled);
        """)
        print("    ✓ Created indexes for alert_definitions")

        # Indexes for alert_annotations
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_annotations_alert_def_id ON alert_annotations(alert_definition_id);
        """)
        print("    ✓ Created indexes for alert_annotations")

        # Indexes for notification_receivers
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_notification_receivers_organization ON notification_receivers(organization);
            CREATE INDEX IF NOT EXISTS idx_notification_receivers_enabled ON notification_receivers(enabled);
        """)
        print("    ✓ Created indexes for notification_receivers")

        # Indexes for routing_rules
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_routing_rules_organization ON routing_rules(organization);
            CREATE INDEX IF NOT EXISTS idx_routing_rules_receiver_id ON routing_rules(receiver_id);
            CREATE INDEX IF NOT EXISTS idx_routing_rules_enabled ON routing_rules(enabled);
            CREATE INDEX IF NOT EXISTS idx_routing_rules_priority ON routing_rules(priority);
            CREATE INDEX IF NOT EXISTS idx_routing_rules_match_severity ON routing_rules(match_severity);
            CREATE INDEX IF NOT EXISTS idx_routing_rules_match_category ON routing_rules(match_category);
        """)
        print("    ✓ Created indexes for routing_rules")

        # Indexes for alert_config_audit_log
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_organization ON alert_config_audit_log(organization);
            CREATE INDEX IF NOT EXISTS idx_audit_log_table_record ON alert_config_audit_log(table_name, record_id);
            CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON alert_config_audit_log(changed_at);
            CREATE INDEX IF NOT EXISTS idx_audit_log_changed_by ON alert_config_audit_log(changed_by);
        """)
        print("    ✓ Created indexes for alert_config_audit_log")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP INDEX IF EXISTS idx_audit_log_changed_by;
            DROP INDEX IF EXISTS idx_audit_log_changed_at;
            DROP INDEX IF EXISTS idx_audit_log_table_record;
            DROP INDEX IF EXISTS idx_audit_log_organization;
            DROP INDEX IF EXISTS idx_routing_rules_match_category;
            DROP INDEX IF EXISTS idx_routing_rules_match_severity;
            DROP INDEX IF EXISTS idx_routing_rules_priority;
            DROP INDEX IF EXISTS idx_routing_rules_enabled;
            DROP INDEX IF EXISTS idx_routing_rules_receiver_id;
            DROP INDEX IF EXISTS idx_routing_rules_organization;
            DROP INDEX IF EXISTS idx_notification_receivers_enabled;
            DROP INDEX IF EXISTS idx_notification_receivers_organization;
            DROP INDEX IF EXISTS idx_alert_annotations_alert_def_id;
            DROP INDEX IF EXISTS idx_alert_definitions_organization_enabled;
            DROP INDEX IF EXISTS idx_alert_definitions_severity;
            DROP INDEX IF EXISTS idx_alert_definitions_category;
            DROP INDEX IF EXISTS idx_alert_definitions_enabled;
            DROP INDEX IF EXISTS idx_alert_definitions_organization;
        """)
        print("    ✓ Dropped dynamic alert config indexes")
