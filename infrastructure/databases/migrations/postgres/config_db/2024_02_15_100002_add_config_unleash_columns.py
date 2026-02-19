from infrastructure.databases.core.base_migration import BaseMigration


class AddConfigUnleashColumns(BaseMigration):
    """Add Unleash integration columns to feature_flags table in config_db."""

    def up(self, adapter):
        """Run the migration."""
        adapter.execute("""
            -- Add unleash_flag_name column
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'feature_flags' 
                    AND column_name = 'unleash_flag_name'
                ) THEN
                    ALTER TABLE feature_flags ADD COLUMN unleash_flag_name VARCHAR(255);
                END IF;
            END $$;

            -- Add last_synced_at column
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'feature_flags' 
                    AND column_name = 'last_synced_at'
                ) THEN
                    ALTER TABLE feature_flags ADD COLUMN last_synced_at TIMESTAMP WITH TIME ZONE;
                END IF;
            END $$;

            -- Add evaluation_count column
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'feature_flags' 
                    AND column_name = 'evaluation_count'
                ) THEN
                    ALTER TABLE feature_flags ADD COLUMN evaluation_count INTEGER DEFAULT 0;
                END IF;
            END $$;

            -- Add last_evaluated_at column
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'feature_flags' 
                    AND column_name = 'last_evaluated_at'
                ) THEN
                    ALTER TABLE feature_flags ADD COLUMN last_evaluated_at TIMESTAMP WITH TIME ZONE;
                END IF;
            END $$;

            -- Add index for Unleash flag name lookups
            CREATE INDEX IF NOT EXISTS idx_feature_flags_unleash_name 
                ON feature_flags(unleash_flag_name);
        """)
        print("    ✓ Added Unleash integration columns to feature_flags table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP INDEX IF EXISTS idx_feature_flags_unleash_name;
            ALTER TABLE feature_flags DROP COLUMN IF EXISTS unleash_flag_name;
            ALTER TABLE feature_flags DROP COLUMN IF EXISTS last_synced_at;
            ALTER TABLE feature_flags DROP COLUMN IF EXISTS evaluation_count;
            ALTER TABLE feature_flags DROP COLUMN IF EXISTS last_evaluated_at;
        """)
        print("    ✓ Removed Unleash integration columns from feature_flags table")
