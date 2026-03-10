from infrastructure.databases.core.base_migration import BaseMigration


class CreateAlertHistoryTable(BaseMigration):
    """Create alert_history table for read-only audit log of triggered alerts."""

    def up(self, adapter):
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS alert_history (
                id BIGSERIAL PRIMARY KEY,
                alert_name VARCHAR(255) NOT NULL,
                category VARCHAR(50) NOT NULL,
                severity VARCHAR(20) NOT NULL,
                triggered_at TIMESTAMPTZ NOT NULL,
                resolved_at TIMESTAMPTZ NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'firing',
                receiver VARCHAR(255) NOT NULL,
                notified_display VARCHAR(500) NULL,
                tenant VARCHAR(255) NULL,
                organization VARCHAR(255) NULL,
                labels JSONB NULL,
                annotations JSONB NULL,
                fingerprint VARCHAR(64) NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_history_triggered_at ON alert_history(triggered_at DESC);
            CREATE INDEX IF NOT EXISTS idx_alert_history_category ON alert_history(category);
            CREATE INDEX IF NOT EXISTS idx_alert_history_severity ON alert_history(severity);
            CREATE INDEX IF NOT EXISTS idx_alert_history_alert_name ON alert_history(alert_name);
            CREATE INDEX IF NOT EXISTS idx_alert_history_tenant ON alert_history(tenant);
        """)
        print("    ✓ Created alert_history table and indexes")

    def down(self, adapter):
        adapter.execute("DROP TABLE IF EXISTS alert_history CASCADE;")
        print("    ✓ Dropped alert_history table")
