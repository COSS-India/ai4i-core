from infrastructure.databases.core.base_migration import BaseMigration


class AddPricePerUnitToServiceConfig(BaseMigration):
    """Add price_per_unit column to service_config table in multi_tenant_db."""

    def up(self, adapter):
        """Run the migration."""
        # Step 1: Add column as nullable
        adapter.execute(
            """
            ALTER TABLE service_config
            ADD COLUMN IF NOT EXISTS price_per_unit NUMERIC(10, 6);
            """
        )
        
        # Step 2: Set default value for any NULL values
        adapter.execute(
            """
            UPDATE service_config
            SET price_per_unit = 0.00
            WHERE price_per_unit IS NULL;
            """
        )
        
        # Step 3: Set column to NOT NULL
        adapter.execute(
            """
            ALTER TABLE service_config
            ALTER COLUMN price_per_unit SET NOT NULL;
            """
        )
        print("    ✓ Added price_per_unit column to service_config table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute(
            """
            ALTER TABLE service_config
            DROP COLUMN IF EXISTS price_per_unit;
            """
        )
        print("    ✓ Dropped price_per_unit column from service_config table")
