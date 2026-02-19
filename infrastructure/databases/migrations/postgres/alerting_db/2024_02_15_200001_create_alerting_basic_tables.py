from infrastructure.databases.core.base_migration import BaseMigration

class CreateAlertingBasicTables(BaseMigration):
    """Create basic alerting tables (alert_rules, alerts, notification_history, escalation_policies, anomaly_detection_models) in alerting_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create alert_rules table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS alert_rules (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                description TEXT,
                metric_name VARCHAR(255) NOT NULL,
                threshold DECIMAL(15,6) NOT NULL,
                operator VARCHAR(10) NOT NULL,
                severity VARCHAR(20) NOT NULL,
                evaluation_window INTEGER DEFAULT 300,
                notification_channels TEXT[],
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100)
            );
        """)
        print("    ✓ Created alert_rules table")

        # Create alerts table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                rule_id INTEGER REFERENCES alert_rules(id) ON DELETE CASCADE,
                metric_name VARCHAR(255) NOT NULL,
                current_value DECIMAL(15,6) NOT NULL,
                threshold DECIMAL(15,6) NOT NULL,
                severity VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'firing',
                fired_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP WITH TIME ZONE,
                acknowledged_at TIMESTAMP WITH TIME ZONE,
                acknowledged_by VARCHAR(100)
            );
        """)
        print("    ✓ Created alerts table")

        # Create notification_history table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS notification_history (
                id SERIAL PRIMARY KEY,
                alert_id INTEGER REFERENCES alerts(id) ON DELETE CASCADE,
                channel VARCHAR(50) NOT NULL,
                recipient VARCHAR(255) NOT NULL,
                status VARCHAR(20) NOT NULL,
                sent_at TIMESTAMP WITH TIME ZONE,
                error_message TEXT
            );
        """)
        print("    ✓ Created notification_history table")

        # Create escalation_policies table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS escalation_policies (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                rules JSONB NOT NULL,
                schedule JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("    ✓ Created escalation_policies table")

        # Create anomaly_detection_models table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS anomaly_detection_models (
                id SERIAL PRIMARY KEY,
                metric_name VARCHAR(255) NOT NULL,
                model_type VARCHAR(50) NOT NULL,
                model_parameters JSONB NOT NULL,
                training_data_size INTEGER NOT NULL,
                last_trained_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                accuracy_score DECIMAL(5,4),
                is_active BOOLEAN DEFAULT true
            );
        """)
        print("    ✓ Created anomaly_detection_models table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS anomaly_detection_models CASCADE;
            DROP TABLE IF EXISTS escalation_policies CASCADE;
            DROP TABLE IF EXISTS notification_history CASCADE;
            DROP TABLE IF EXISTS alerts CASCADE;
            DROP TABLE IF EXISTS alert_rules CASCADE;
        """)
        print("    ✓ Dropped basic alerting tables")
