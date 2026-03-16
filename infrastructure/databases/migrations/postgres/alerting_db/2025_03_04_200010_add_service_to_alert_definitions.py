from infrastructure.databases.core.base_migration import BaseMigration


class AddServiceToAlertDefinitions(BaseMigration):
    """Add service column to alert_definitions for optional service-scoped PromQL (service label in expressions)."""

    def up(self, adapter):
        """Add service column if it does not exist."""
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alert_definitions' AND column_name = 'service') THEN
                    ALTER TABLE alert_definitions ADD COLUMN service TEXT[] NULL;
                END IF;
            END $$;
        """)
        print("    ✓ Added service to alert_definitions")

    def down(self, adapter):
        """Remove service column."""
        adapter.execute("""
            ALTER TABLE alert_definitions DROP COLUMN IF EXISTS service;
        """)
        print("    ✓ Dropped service from alert_definitions")
