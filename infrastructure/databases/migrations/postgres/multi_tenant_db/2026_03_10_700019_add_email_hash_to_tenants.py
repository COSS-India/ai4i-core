from infrastructure.databases.core.base_migration import BaseMigration


class AddEmailHashToTenants(BaseMigration):
    """
    Add email_hash column to tenants for efficient, hashed email lookups.

    - Adds nullable VARCHAR(500) email_hash column
    - Ensures uniqueness via a unique constraint
    - Adds an index (in addition to the unique index) for explicit query planning, if needed
    """

    def up(self, adapter):
        """Run the migration."""
        adapter.execute(
            """
            ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS email_hash VARCHAR(500) NULL;

            -- PostgreSQL does not support IF NOT EXISTS for ADD CONSTRAINT,
            -- but migrations are applied only once per environment, so this is safe.
            ALTER TABLE tenants
            ADD CONSTRAINT tenants_email_hash_key UNIQUE (email_hash);

            CREATE INDEX IF NOT EXISTS idx_tenants_email_hash
                ON tenants (email_hash);
            """
        )
        print("    ✓ Added email_hash column, unique constraint, and index on tenants in multi_tenant_db")

    def down(self, adapter):
        """Rollback the migration (drop index, constraint, and column)."""
        adapter.execute(
            """
            DROP INDEX IF EXISTS idx_tenants_email_hash;

            ALTER TABLE tenants
            DROP CONSTRAINT IF EXISTS tenants_email_hash_key;

            ALTER TABLE tenants
            DROP COLUMN IF EXISTS email_hash;
            """
        )
        print("    ✓ Removed email_hash column, constraint, and index from tenants in multi_tenant_db")

