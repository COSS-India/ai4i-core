from infrastructure.databases.core.base_migration import BaseMigration

class AddAuthRemainingColumns(BaseMigration):
    """Add remaining columns to users table (is_tenant, selected_api_key_id) in auth_db."""

    def up(self, adapter):
        """Run the migration."""
        # Add is_tenant column
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users' 
                    AND column_name = 'is_tenant'
                ) THEN
                    ALTER TABLE users ADD COLUMN is_tenant BOOLEAN DEFAULT NULL;
                END IF;
            END $$;
        """)
        print("    ✓ Added is_tenant column to users table")

        # Add selected_api_key_id column
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users' 
                    AND column_name = 'selected_api_key_id'
                ) THEN
                    ALTER TABLE users ADD COLUMN selected_api_key_id INTEGER;
                END IF;
            END $$;
        """)
        print("    ✓ Added selected_api_key_id column to users table")

        # Add foreign key constraint for selected_api_key_id
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.table_constraints 
                    WHERE constraint_name = 'users_selected_api_key_id_fkey' 
                    AND table_name = 'users'
                ) THEN
                    ALTER TABLE users
                        ADD CONSTRAINT users_selected_api_key_id_fkey
                        FOREIGN KEY (selected_api_key_id) REFERENCES api_keys(id) ON DELETE SET NULL;
                END IF;
            END $$;
        """)
        print("    ✓ Added foreign key constraint for selected_api_key_id")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            ALTER TABLE users DROP CONSTRAINT IF EXISTS users_selected_api_key_id_fkey;
            ALTER TABLE users DROP COLUMN IF EXISTS selected_api_key_id;
            ALTER TABLE users DROP COLUMN IF EXISTS is_tenant;
        """)
        print("    ✓ Removed additional columns from users table")
