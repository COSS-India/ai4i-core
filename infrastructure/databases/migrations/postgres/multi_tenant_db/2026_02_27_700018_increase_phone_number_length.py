from infrastructure.databases.core.base_migration import BaseMigration


class IncreasePhoneNumberLength(BaseMigration):
    """
    Increase phone_number column size to VARCHAR(500) in both tenants and tenant_users tables.
    This aligns with encrypted phone numbers, which can exceed the previous VARCHAR(50) limit.
    """

    def up(self, adapter):
        """Run the migration."""
        # Ensure tenants.phone_number exists and is VARCHAR(500)
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
        print("    ✓ Ensured tenants.phone_number is VARCHAR(500) in multi_tenant_db")

        # Ensure tenant_users.phone_number exists and is VARCHAR(500)
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
        print("    ✓ Ensured tenant_users.phone_number is VARCHAR(500) in multi_tenant_db")

    def down(self, adapter):
        """
        Rollback the migration.
        Note: We revert phone_number columns to VARCHAR(50); this may fail if data exceeds the limit.
        """
        adapter.execute(
            """
            ALTER TABLE tenants
            ALTER COLUMN phone_number TYPE VARCHAR(50);

            ALTER TABLE tenant_users
            ALTER COLUMN phone_number TYPE VARCHAR(50);
            """
        )
        print("    ✓ Reverted phone_number columns to VARCHAR(50) in tenants and tenant_users")

