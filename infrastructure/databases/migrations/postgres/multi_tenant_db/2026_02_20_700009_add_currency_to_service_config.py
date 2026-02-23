from infrastructure.databases.core.base_migration import BaseMigration


class AddCurrencyToServiceConfig(BaseMigration):
    """Add currency column to service_config table in multi_tenant_db."""

    def up(self, adapter):
        """Run the migration."""
        # Step 1: Add column as nullable
        adapter.execute(
            """
            ALTER TABLE service_config
            ADD COLUMN IF NOT EXISTS currency VARCHAR(10);
            """
        )
        
        # Step 2: Set default value for any NULL values
        adapter.execute(
            """
            UPDATE service_config
            SET currency = 'INR'
            WHERE currency IS NULL;
            """
        )
        
        # Step 3: Set column to NOT NULL with default
        adapter.execute(
            """
            ALTER TABLE service_config
            ALTER COLUMN currency SET NOT NULL,
            ALTER COLUMN currency SET DEFAULT 'INR';
            """
        )
        print("    ✓ Added currency column to service_config table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute(
            """
            ALTER TABLE service_config
            DROP COLUMN IF EXISTS currency;
            """
        )
        print("    ✓ Dropped currency column from service_config table")
