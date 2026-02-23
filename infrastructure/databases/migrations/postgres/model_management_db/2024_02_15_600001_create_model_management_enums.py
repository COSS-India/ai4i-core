from infrastructure.databases.core.base_migration import BaseMigration

class CreateModelManagementEnums(BaseMigration):
    """Create enum types for model management in model_management_db."""

    def up(self, adapter):
        """Run the migration."""
        # Enable pgcrypto extension for UUID generation
        adapter.execute("""
            CREATE EXTENSION IF NOT EXISTS "pgcrypto";
        """)
        print("    ✓ Enabled pgcrypto extension")

        # Create version_status enum type
        adapter.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'version_status') THEN
                    CREATE TYPE version_status AS ENUM ('ACTIVE', 'DEPRECATED');
                END IF;
            END $$;
        """)
        print("    ✓ Created version_status enum")

        # Create experiment_status enum type
        adapter.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'experiment_status') THEN
                    CREATE TYPE experiment_status AS ENUM ('DRAFT', 'RUNNING', 'PAUSED', 'COMPLETED', 'CANCELLED');
                END IF;
            END $$;
        """)
        print("    ✓ Created experiment_status enum")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TYPE IF EXISTS experiment_status CASCADE;
            DROP TYPE IF EXISTS version_status CASCADE;
        """)
        print("    ✓ Dropped model management enums")
