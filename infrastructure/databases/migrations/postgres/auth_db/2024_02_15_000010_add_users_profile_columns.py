"""
Add profile and preference columns to users table so auth-service User model matches DB.
Auth-service expects: full_name, is_superuser, last_login, preferences, avatar_url,
phone_number, timezone, language. These were missing and caused login 500.
"""
from infrastructure.databases.core.base_migration import BaseMigration


class AddUsersProfileColumns(BaseMigration):
    """Add profile and preference columns to users table in auth_db."""

    def up(self, adapter):
        """Add missing columns expected by auth-service User model."""
        columns_to_add = [
            ("full_name", "VARCHAR(255)"),
            ("is_superuser", "BOOLEAN DEFAULT false"),
            ("last_login", "TIMESTAMP WITH TIME ZONE"),
            ("preferences", "JSONB DEFAULT '{}'"),
            ("avatar_url", "VARCHAR(500)"),
            ("phone_number", "VARCHAR(20)"),
            ("timezone", "VARCHAR(50) DEFAULT 'UTC'"),
            ("language", "VARCHAR(10) DEFAULT 'en'"),
        ]
        for col_name, col_def in columns_to_add:
            adapter.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = '{col_name}'
                    ) THEN
                        ALTER TABLE users ADD COLUMN {col_name} {col_def};
                    END IF;
                END $$;
            """)
            print(f"    ✓ Ensured users.{col_name} exists")
        print("    ✓ Users profile columns added")

    def down(self, adapter):
        """Remove added columns."""
        for col in [
            "full_name", "is_superuser", "last_login", "preferences",
            "avatar_url", "phone_number", "timezone", "language"
        ]:
            adapter.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {col};")
        print("    ✓ Removed users profile columns")
