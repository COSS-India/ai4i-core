from infrastructure.databases.core.base_migration import BaseMigration


class AddRuleNameToNotificationReceivers(BaseMigration):
    """Add optional rule_name to notification_receivers (for future deprecation of routing_rules table)."""

    def up(self, adapter):
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'notification_receivers' AND column_name = 'rule_name') THEN
                    ALTER TABLE notification_receivers ADD COLUMN rule_name VARCHAR(255) NULL;
                END IF;
            END $$;
        """)
        print("    ✓ Added rule_name to notification_receivers")

    def down(self, adapter):
        adapter.execute("ALTER TABLE notification_receivers DROP COLUMN IF EXISTS rule_name;")
        print("    ✓ Dropped rule_name from notification_receivers")
