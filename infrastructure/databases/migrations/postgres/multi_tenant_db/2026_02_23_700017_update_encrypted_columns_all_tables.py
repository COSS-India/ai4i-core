from infrastructure.databases.core.base_migration import BaseMigration


class UpdateEncryptedColumnsAllTables(BaseMigration):
    """
    Update email and phone_number columns in both tenants and tenant_users tables to VARCHAR(500) 
    to accommodate encrypted values.
    Encrypted email and phone numbers are longer than the original VARCHAR(320) and VARCHAR(50) sizes.
    """

    def up(self, adapter):
        """Run the migration."""
        # Update tenants table columns
        adapter.execute(
            """
            ALTER TABLE tenants
            ALTER COLUMN contact_email TYPE VARCHAR(500);
            """
        )
        print("    ✓ Updated contact_email column to VARCHAR(500) in tenants table")

        # Update tenants phone_number
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public'
                    AND table_name = 'tenants' 
                    AND column_name = 'phone_number'
                ) THEN
                    ALTER TABLE tenants 
                    ALTER COLUMN phone_number TYPE VARCHAR(500);
                ELSE
                    ALTER TABLE tenants 
                    ADD COLUMN phone_number VARCHAR(500) NULL;
                END IF;
            END $$;
            """
        )
        print("    ✓ Updated phone_number column to VARCHAR(500) in tenants table")

        # Update tenant_users table columns
        adapter.execute(
            """
            ALTER TABLE tenant_users
            ALTER COLUMN email TYPE VARCHAR(500);
            """
        )
        print("    ✓ Updated email column to VARCHAR(500) in tenant_users table")

        # Update tenant_users phone_number
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public'
                    AND table_name = 'tenant_users' 
                    AND column_name = 'phone_number'
                ) THEN
                    ALTER TABLE tenant_users 
                    ALTER COLUMN phone_number TYPE VARCHAR(500);
                ELSE
                    ALTER TABLE tenant_users 
                    ADD COLUMN phone_number VARCHAR(500) NULL;
                END IF;
            END $$;
            """
        )
        print("    ✓ Updated phone_number column to VARCHAR(500) in tenant_users table")

    def down(self, adapter):
        """
        Rollback the migration.
        Note: We revert to smaller sizes, but this may fail if existing data exceeds the limits.
        """
        adapter.execute(
            """
            ALTER TABLE tenants
            ALTER COLUMN contact_email TYPE VARCHAR(320);

            ALTER TABLE tenants
            ALTER COLUMN phone_number TYPE VARCHAR(50);

            ALTER TABLE tenant_users
            ALTER COLUMN email TYPE VARCHAR(320);

            ALTER TABLE tenant_users
            ALTER COLUMN phone_number TYPE VARCHAR(50);
            """
        )
        print("    ✓ Reverted all encrypted columns to original sizes")
