from infrastructure.databases.core.base_migration import BaseMigration


class AddServicesPolicyColumn(BaseMigration):
    """Add policy JSONB column to services table for storing latency, cost, and accuracy policies."""

    def up(self, adapter):
        """Run the migration."""
        adapter.execute("""
            -- Add policy column to services table
            ALTER TABLE services 
            ADD COLUMN IF NOT EXISTS policy JSONB;

            -- Add comment to document the column
            COMMENT ON COLUMN services.policy IS 'Policy data (latency, cost, accuracy) stored as JSONB. Example: {"latency": "low", "cost": "tier_3", "accuracy": "sensitive"}';

            -- Create GIN index on policy column for better query performance
            CREATE INDEX IF NOT EXISTS idx_services_policy ON services USING GIN (policy);
        """)
        print("    ✓ Added policy JSONB column to services table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP INDEX IF EXISTS idx_services_policy;
            ALTER TABLE services DROP COLUMN IF EXISTS policy;
        """)
        print("    ✓ Removed policy column from services table")
