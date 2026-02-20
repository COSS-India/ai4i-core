from infrastructure.databases.core.base_migration import BaseMigration


class FixTenantEmailVerificationsSchema(BaseMigration):
    """Fix tenant_email_verifications table to match model: rename tenant_uuid to tenant_id, rename verification_token to token, remove email column."""

    def up(self, adapter):
        """Run the migration."""
        # Step 1: Rename tenant_uuid to tenant_id if it exists
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_email_verifications' 
                    AND column_name = 'tenant_uuid'
                ) THEN
                    ALTER TABLE tenant_email_verifications
                    RENAME COLUMN tenant_uuid TO tenant_id;
                END IF;
            END $$;
            """
        )
        
        # Step 2: Rename verification_token to token if it exists
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_email_verifications' 
                    AND column_name = 'verification_token'
                ) THEN
                    ALTER TABLE tenant_email_verifications
                    RENAME COLUMN verification_token TO token;
                END IF;
            END $$;
            """
        )
        
        # Step 3: Update token column type to VARCHAR(512) to match model
        adapter.execute(
            """
            ALTER TABLE tenant_email_verifications
            ALTER COLUMN token TYPE VARCHAR(512);
            """
        )
        
        # Step 4: Remove email column if it exists
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_email_verifications' 
                    AND column_name = 'email'
                ) THEN
                    ALTER TABLE tenant_email_verifications DROP COLUMN email;
                END IF;
            END $$;
            """
        )
        
        print("    ✓ Fixed tenant_email_verifications schema")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_email_verifications' 
                    AND column_name = 'tenant_id'
                ) THEN
                    ALTER TABLE tenant_email_verifications
                    RENAME COLUMN tenant_id TO tenant_uuid;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_email_verifications' 
                    AND column_name = 'token'
                ) THEN
                    ALTER TABLE tenant_email_verifications
                    RENAME COLUMN token TO verification_token;
                END IF;
            END $$;
            """
        )
        print("    ✓ Rolled back tenant_email_verifications schema changes")
