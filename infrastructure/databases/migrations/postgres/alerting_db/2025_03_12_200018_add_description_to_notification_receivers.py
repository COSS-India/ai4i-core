from infrastructure.databases.core.base_migration import BaseMigration


class AddDescriptionToNotificationReceivers(BaseMigration):
    """Add optional description to notification_receivers."""

    def up(self, adapter):
        adapter.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'notification_receivers' AND column_name = 'description') THEN
                    ALTER TABLE notification_receivers ADD COLUMN description TEXT NULL;
                END IF;
            END $$;
            """
        )
        print("    ✓ Added description to notification_receivers")

    def down(self, adapter):
        adapter.execute(
            "ALTER TABLE notification_receivers DROP COLUMN IF EXISTS description;"
        )
        print("    ✓ Dropped description from notification_receivers")

