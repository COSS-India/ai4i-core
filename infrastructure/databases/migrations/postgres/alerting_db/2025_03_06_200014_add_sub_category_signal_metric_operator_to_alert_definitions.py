from infrastructure.databases.core.base_migration import BaseMigration


class AddSubCategorySignalMetricOperatorToAlertDefinitions(BaseMigration):
    """Add sub_category, signal, signal_metric, condition_operator to alert_definitions for configurable PromQL."""

    def up(self, adapter):
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alert_definitions' AND column_name = 'sub_category') THEN
                    ALTER TABLE alert_definitions ADD COLUMN sub_category VARCHAR(100) NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alert_definitions' AND column_name = 'signal') THEN
                    ALTER TABLE alert_definitions ADD COLUMN signal VARCHAR(100) NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alert_definitions' AND column_name = 'signal_metric') THEN
                    ALTER TABLE alert_definitions ADD COLUMN signal_metric VARCHAR(100) NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alert_definitions' AND column_name = 'condition_operator') THEN
                    ALTER TABLE alert_definitions ADD COLUMN condition_operator VARCHAR(10) NULL;
                END IF;
            END $$;
        """)
        print("    ✓ Added sub_category, signal, signal_metric, condition_operator to alert_definitions")

    def down(self, adapter):
        adapter.execute("ALTER TABLE alert_definitions DROP COLUMN IF EXISTS sub_category;")
        adapter.execute("ALTER TABLE alert_definitions DROP COLUMN IF EXISTS signal;")
        adapter.execute("ALTER TABLE alert_definitions DROP COLUMN IF EXISTS signal_metric;")
        adapter.execute("ALTER TABLE alert_definitions DROP COLUMN IF EXISTS condition_operator;")
        print("    ✓ Dropped sub_category, signal, signal_metric, condition_operator from alert_definitions")
