from infrastructure.databases.core.base_migration import BaseMigration


class AddUnitTypeToServiceConfig(BaseMigration):
    """Add unit_type column to service_config table in multi_tenant_db."""

    def up(self, adapter):
        """Run the migration."""
        # Step 1: Add column as nullable
        adapter.execute(
            """
            ALTER TABLE service_config
            ADD COLUMN IF NOT EXISTS unit_type VARCHAR(50);
            """
        )
        
        # Step 2: Update existing rows based on pricing_model
        adapter.execute(
            """
            UPDATE service_config
            SET unit_type = CASE
                WHEN pricing_model = 'PAY_PER_MINUTE' THEN 'minute'
                WHEN pricing_model = 'PAY_PER_CHARACTER' THEN 'character'
                WHEN pricing_model = 'PAY_PER_TOKEN' THEN 'request'
                WHEN pricing_model = 'PAY_PER_IMAGE' THEN 'request'
                WHEN pricing_model = 'PAY_PER_REQUEST' THEN 'request'
                ELSE 'request'
            END
            WHERE unit_type IS NULL;
            """
        )
        
        # Step 3: Set column to NOT NULL
        adapter.execute(
            """
            ALTER TABLE service_config
            ALTER COLUMN unit_type SET NOT NULL;
            """
        )
        print("    ✓ Added unit_type column to service_config table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute(
            """
            ALTER TABLE service_config
            DROP COLUMN IF EXISTS unit_type;
            """
        )
        print("    ✓ Dropped unit_type column from service_config table")
