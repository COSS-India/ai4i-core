from infrastructure.databases.core.base_migration import BaseMigration


class AlertDefinitionGlobalUniqueName(BaseMigration):
    """Change alert_definitions uniqueness from (organization, name) to global (name) only."""

    def up(self, adapter):
        # Drop the organization-scoped unique constraint
        adapter.execute("""
            ALTER TABLE alert_definitions
            DROP CONSTRAINT IF EXISTS unique_organization_alert_name;
        """)
        # Add global unique constraint on name (case-insensitive via unique index on LOWER(name))
        adapter.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS unique_alert_definitions_name_lower
            ON alert_definitions (LOWER(TRIM(name)));
        """)
        print("    ✓ Changed alert_definitions to globally unique name (unique_alert_definitions_name_lower)")

    def down(self, adapter):
        adapter.execute("""
            DROP INDEX IF EXISTS unique_alert_definitions_name_lower;
        """)
        adapter.execute("""
            ALTER TABLE alert_definitions
            ADD CONSTRAINT unique_organization_alert_name UNIQUE (organization, name);
        """)
        print("    ✓ Restored unique_organization_alert_name on alert_definitions")
