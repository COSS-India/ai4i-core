from infrastructure.databases.core.base_migration import BaseMigration


class AddCategorySeverityToNotificationReceivers(BaseMigration):
    """Add category and severity to notification_receivers (store on receiver; no dependency on routing_rules)."""

    def up(self, adapter):
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'notification_receivers' AND column_name = 'category') THEN
                    ALTER TABLE notification_receivers ADD COLUMN category VARCHAR(50) NOT NULL DEFAULT 'application';
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'notification_receivers' AND column_name = 'severity') THEN
                    ALTER TABLE notification_receivers ADD COLUMN severity VARCHAR(20) NOT NULL DEFAULT 'warning';
                END IF;
            END $$;
        """)
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_notification_receivers_category ON notification_receivers(category);
            CREATE INDEX IF NOT EXISTS idx_notification_receivers_severity ON notification_receivers(severity);
        """)
        print("    ✓ Added category and severity to notification_receivers")

    def down(self, adapter):
        adapter.execute("DROP INDEX IF EXISTS idx_notification_receivers_category;")
        adapter.execute("DROP INDEX IF EXISTS idx_notification_receivers_severity;")
        adapter.execute("ALTER TABLE notification_receivers DROP COLUMN IF EXISTS category;")
        adapter.execute("ALTER TABLE notification_receivers DROP COLUMN IF EXISTS severity;")
        print("    ✓ Dropped category and severity from notification_receivers")
