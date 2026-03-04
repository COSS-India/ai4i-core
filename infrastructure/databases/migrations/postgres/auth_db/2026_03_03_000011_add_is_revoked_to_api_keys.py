from infrastructure.databases.core.base_migration import BaseMigration


class AddIsRevokedToApiKeys(BaseMigration):
    """Add is_revoked flag to api_keys table to support permanent revocation."""

    def up(self, adapter):
        """Run the migration."""
        adapter.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'api_keys'
                      AND column_name = 'is_revoked'
                ) THEN
                    ALTER TABLE api_keys
                    ADD COLUMN is_revoked BOOLEAN NOT NULL DEFAULT FALSE;
                END IF;
            END $$;
            """
        )
        print("    ✓ Added is_revoked column to api_keys table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute(
            """
            ALTER TABLE api_keys
            DROP COLUMN IF EXISTS is_revoked;
            """
        )
        print("    ✓ Removed is_revoked column from api_keys table")

