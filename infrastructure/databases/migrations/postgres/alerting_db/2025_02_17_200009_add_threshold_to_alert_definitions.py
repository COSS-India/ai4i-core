from infrastructure.databases.core.base_migration import BaseMigration


class AddThresholdToAlertDefinitions(BaseMigration):
    """Add threshold_value and threshold_unit to alert_definitions for threshold-based PromQL generation."""

    def up(self, adapter):
        """Add columns if they do not exist."""
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'alert_definitions' AND column_name = 'threshold_value') THEN
                    ALTER TABLE alert_definitions ADD COLUMN threshold_value DOUBLE PRECISION;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'alert_definitions' AND column_name = 'threshold_unit') THEN
                    ALTER TABLE alert_definitions ADD COLUMN threshold_unit VARCHAR(50);
                END IF;
            END $$;
        """)
        print("    ✓ Added threshold_value, threshold_unit to alert_definitions")

    def down(self, adapter):
        """Remove columns."""
        adapter.execute("""
            ALTER TABLE alert_definitions DROP COLUMN IF EXISTS threshold_value;
            ALTER TABLE alert_definitions DROP COLUMN IF EXISTS threshold_unit;
        """)
        print("    ✓ Dropped threshold_value, threshold_unit from alert_definitions")
