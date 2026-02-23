from infrastructure.databases.core.base_migration import BaseMigration

class CreateDynamicAlertConfigTables(BaseMigration):
    """Create dynamic alert configuration tables (alert_definitions, alert_annotations, notification_receivers, routing_rules) in alerting_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create alert_definitions table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS alert_definitions (
                id SERIAL PRIMARY KEY,
                organization VARCHAR(100) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                promql_expr TEXT NOT NULL,
                category VARCHAR(50) NOT NULL DEFAULT 'application',
                severity VARCHAR(20) NOT NULL,
                urgency VARCHAR(20) DEFAULT 'medium',
                alert_type VARCHAR(50),
                scope VARCHAR(50),
                evaluation_interval VARCHAR(20) DEFAULT '30s',
                for_duration VARCHAR(20) DEFAULT '5m',
                enabled BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100),
                updated_by VARCHAR(100),
                CONSTRAINT unique_organization_alert_name UNIQUE (organization, name)
            );
        """)
        print("    ✓ Created alert_definitions table")

        # Create alert_annotations table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS alert_annotations (
                id SERIAL PRIMARY KEY,
                alert_definition_id INTEGER NOT NULL REFERENCES alert_definitions(id) ON DELETE CASCADE,
                annotation_key VARCHAR(50) NOT NULL,
                annotation_value TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT unique_alert_annotation_key UNIQUE (alert_definition_id, annotation_key)
            );
        """)
        print("    ✓ Created alert_annotations table")

        # Create notification_receivers table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS notification_receivers (
                id SERIAL PRIMARY KEY,
                organization VARCHAR(100) NOT NULL,
                receiver_name VARCHAR(255) NOT NULL,
                email_to TEXT[] NOT NULL,
                email_subject_template TEXT,
                email_body_template TEXT,
                enabled BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100),
                CONSTRAINT unique_organization_receiver_name UNIQUE (organization, receiver_name)
            );
        """)
        print("    ✓ Created notification_receivers table")

        # Create routing_rules table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS routing_rules (
                id SERIAL PRIMARY KEY,
                organization VARCHAR(100) NOT NULL,
                rule_name VARCHAR(255) NOT NULL,
                receiver_id INTEGER NOT NULL REFERENCES notification_receivers(id) ON DELETE CASCADE,
                match_severity VARCHAR(20),
                match_category VARCHAR(50),
                match_alert_type VARCHAR(50),
                group_by TEXT[],
                group_wait VARCHAR(20) DEFAULT '10s',
                group_interval VARCHAR(20) DEFAULT '10s',
                repeat_interval VARCHAR(20) DEFAULT '12h',
                continue_routing BOOLEAN DEFAULT false,
                priority INTEGER DEFAULT 100,
                enabled BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100),
                CONSTRAINT unique_organization_rule_name UNIQUE (organization, rule_name)
            );
        """)
        print("    ✓ Created routing_rules table")

        # Create alert_config_audit_log table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS alert_config_audit_log (
                id SERIAL PRIMARY KEY,
                organization VARCHAR(100),
                table_name VARCHAR(50) NOT NULL,
                record_id INTEGER NOT NULL,
                operation VARCHAR(20) NOT NULL,
                changed_by VARCHAR(100) NOT NULL,
                changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                before_values JSONB,
                after_values JSONB,
                change_description TEXT
            );
        """)
        print("    ✓ Created alert_config_audit_log table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS alert_config_audit_log CASCADE;
            DROP TABLE IF EXISTS routing_rules CASCADE;
            DROP TABLE IF EXISTS notification_receivers CASCADE;
            DROP TABLE IF EXISTS alert_annotations CASCADE;
            DROP TABLE IF EXISTS alert_definitions CASCADE;
        """)
        print("    ✓ Dropped dynamic alert config tables")
