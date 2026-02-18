from infrastructure.databases.core.base_migration import BaseMigration


class UpdateTenantStatusAndPhoneColumns(BaseMigration):
    """
    Align multi_tenant_db schema with application models:
    - Ensure status columns use VARCHAR(50) (to support values like DEACTIVATED)
    - Add phone_number columns to tenants and tenant_users
    """

    def up(self, adapter):
        """Run the migration."""
        # Align status columns
        adapter.execute(
            """
            ALTER TABLE tenants
            ALTER COLUMN status TYPE VARCHAR(50);

            ALTER TABLE tenant_users
            ALTER COLUMN status TYPE VARCHAR(50);

            ALTER TABLE user_billing_records
            ALTER COLUMN status TYPE VARCHAR(50);

            -- In migration-based schema, tenant_billing_records uses 'status' column
            -- (init-all-databases.sql path uses billing_status, handled separately)
            ALTER TABLE tenant_billing_records
            ALTER COLUMN status TYPE VARCHAR(50);
            """
        )
        print("    ✓ Updated status columns to VARCHAR(50) in multi_tenant_db")

        # Add phone_number columns (idempotent)
        adapter.execute(
            """
            ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50) NULL;

            ALTER TABLE tenant_users
            ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50) NULL;
            """
        )
        print("    ✓ Added phone_number columns to tenants and tenant_users in multi_tenant_db")

    def down(self, adapter):
        """
        Rollback the migration.
        Note: We only drop the newly added phone_number columns.
        We do not revert status column lengths since shrinking types can be destructive.
        """
        adapter.execute(
            """
            ALTER TABLE tenant_users
            DROP COLUMN IF EXISTS phone_number;

            ALTER TABLE tenants
            DROP COLUMN IF EXISTS phone_number;
            """
        )
        print("    ✓ Dropped phone_number columns from tenants and tenant_users in multi_tenant_db")

