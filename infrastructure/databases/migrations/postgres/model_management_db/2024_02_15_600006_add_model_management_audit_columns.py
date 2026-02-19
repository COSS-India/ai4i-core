from infrastructure.databases.core.base_migration import BaseMigration


class AddModelManagementAuditColumns(BaseMigration):
    """Add created_by and updated_by columns to models and services tables for audit tracking."""

    def up(self, adapter):
        """Run the migration."""
        adapter.execute("""
            -- ========================================================================
            -- Add created_by and updated_by columns to models table
            -- ========================================================================
            DO $$
            BEGIN
                -- Add created_by column if it doesn't exist
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'models' 
                    AND column_name = 'created_by'
                ) THEN
                    ALTER TABLE models ADD COLUMN created_by VARCHAR(255) DEFAULT NULL;
                END IF;

                -- Add updated_by column if it doesn't exist
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'models' 
                    AND column_name = 'updated_by'
                ) THEN
                    ALTER TABLE models ADD COLUMN updated_by VARCHAR(255) DEFAULT NULL;
                END IF;
            END $$;

            -- Add comments to document the columns
            COMMENT ON COLUMN models.created_by IS 'User ID (string) who created this model';
            COMMENT ON COLUMN models.updated_by IS 'User ID (string) who last updated this model';

            -- Create index for filtering by created_by
            CREATE INDEX IF NOT EXISTS idx_models_created_by ON models(created_by);

            -- ========================================================================
            -- Add created_by and updated_by columns to services table
            -- ========================================================================
            DO $$
            BEGIN
                -- Add created_by column if it doesn't exist
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'services' 
                    AND column_name = 'created_by'
                ) THEN
                    ALTER TABLE services ADD COLUMN created_by VARCHAR(255) DEFAULT NULL;
                END IF;

                -- Add updated_by column if it doesn't exist
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'services' 
                    AND column_name = 'updated_by'
                ) THEN
                    ALTER TABLE services ADD COLUMN updated_by VARCHAR(255) DEFAULT NULL;
                END IF;
            END $$;

            -- Add comments to document the columns
            COMMENT ON COLUMN services.created_by IS 'User ID (string) who created this service';
            COMMENT ON COLUMN services.updated_by IS 'User ID (string) who last updated this service';

            -- Create index for filtering by created_by
            CREATE INDEX IF NOT EXISTS idx_services_created_by ON services(created_by);
        """)
        print("    ✓ Added created_by and updated_by columns to models and services tables")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            -- Drop indexes
            DROP INDEX IF EXISTS idx_models_created_by;
            DROP INDEX IF EXISTS idx_services_created_by;

            -- Drop columns from models table
            ALTER TABLE models DROP COLUMN IF EXISTS created_by;
            ALTER TABLE models DROP COLUMN IF EXISTS updated_by;

            -- Drop columns from services table
            ALTER TABLE services DROP COLUMN IF EXISTS created_by;
            ALTER TABLE services DROP COLUMN IF EXISTS updated_by;
        """)
        print("    ✓ Removed audit columns from models and services tables")
