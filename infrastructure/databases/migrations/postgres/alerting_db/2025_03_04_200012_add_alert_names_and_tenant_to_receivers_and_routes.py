from infrastructure.databases.core.base_migration import BaseMigration


class AddAlertNamesAndTenantToReceiversAndRoutes(BaseMigration):
    """Add optional alert_names and tenant to notification_receivers; match_alert_names and match_tenant_id to routing_rules."""

    def up(self, adapter):
        # notification_receivers: optional alert_names (specific alert definitions) and tenant (name; resolved to tenant_id in sync)
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'notification_receivers' AND column_name = 'alert_names') THEN
                    ALTER TABLE notification_receivers ADD COLUMN alert_names TEXT[] NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'notification_receivers' AND column_name = 'tenant') THEN
                    ALTER TABLE notification_receivers ADD COLUMN tenant VARCHAR(255) NULL;
                END IF;
            END $$;
        """)
        print("    ✓ Added alert_names and tenant to notification_receivers")

        # routing_rules: match_alert_names (from receiver), match_tenant_id (resolved from receiver.tenant in sync)
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'routing_rules' AND column_name = 'match_alert_names') THEN
                    ALTER TABLE routing_rules ADD COLUMN match_alert_names TEXT[] NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'routing_rules' AND column_name = 'match_tenant_id') THEN
                    ALTER TABLE routing_rules ADD COLUMN match_tenant_id VARCHAR(255) NULL;
                END IF;
            END $$;
        """)
        print("    ✓ Added match_alert_names and match_tenant_id to routing_rules")

    def down(self, adapter):
        adapter.execute("ALTER TABLE notification_receivers DROP COLUMN IF EXISTS alert_names;")
        adapter.execute("ALTER TABLE notification_receivers DROP COLUMN IF EXISTS tenant;")
        adapter.execute("ALTER TABLE routing_rules DROP COLUMN IF EXISTS match_alert_names;")
        adapter.execute("ALTER TABLE routing_rules DROP COLUMN IF EXISTS match_tenant_id;")
        print("    ✓ Dropped alert_names and tenant from notification_receivers; match_alert_names and match_tenant_id from routing_rules")
