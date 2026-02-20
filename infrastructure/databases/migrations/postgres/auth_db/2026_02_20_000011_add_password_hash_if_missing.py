"""
Add password_hash to users if missing (auth_db).

Useful when the users table was created without this column (e.g. by another
schema or partial migrations). Idempotent: safe to run even if column exists.
"""
from infrastructure.databases.core.base_migration import BaseMigration


class AddPasswordHashIfMissing(BaseMigration):
    """Add password_hash column to users table if it does not exist."""

    def up(self, adapter):
        """Run the migration."""
        adapter.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'users'
                      AND column_name = 'password_hash'
                ) THEN
                    ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL;
                    COMMENT ON COLUMN users.password_hash IS 'Password hash for traditional login. NULL for OAuth-only users.';
                END IF;
            END $$;
        """)
        print("    ✓ Ensured password_hash column exists on users table")

    def down(self, adapter):
        """Rollback: remove column only if this migration added it. We cannot know for sure, so we use IF EXISTS."""
        adapter.execute("""
            ALTER TABLE users DROP COLUMN IF EXISTS password_hash;
        """)
        print("    ✓ Dropped password_hash column from users table (if present)")
