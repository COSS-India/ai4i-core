from infrastructure.databases.core.base_migration import BaseMigration

class MakePasswordNullableForOauth(BaseMigration):
    """Make password_hash column nullable to support OAuth-only users in auth_db."""

    def up(self, adapter):
        """Run the migration."""
        # Alter users table to allow NULL passwords (for OAuth users)
        adapter.execute("""
            ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
        """)
        print("    ✓ Made password_hash nullable for OAuth users")

        # Add comment to document the change
        adapter.execute("""
            COMMENT ON COLUMN users.password_hash IS 'Password hash for traditional login. NULL for OAuth-only users.';
        """)
        print("    ✓ Added comment for password_hash column")

    def down(self, adapter):
        """Rollback the migration."""
        # Note: This rollback will fail if there are users with NULL passwords
        adapter.execute("""
            UPDATE users SET password_hash = '' WHERE password_hash IS NULL;
            ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;
        """)
        print("    ✓ Made password_hash required (rollback)")
