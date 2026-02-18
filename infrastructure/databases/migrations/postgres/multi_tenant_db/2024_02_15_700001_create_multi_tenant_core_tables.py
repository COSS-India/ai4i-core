from infrastructure.databases.core.base_migration import BaseMigration

class CreateMultiTenantCoreTables(BaseMigration):
    """Create core multi-tenant tables (tenants, tenant_billing_records, tenant_audit_logs) in multi_tenant_db PUBLIC schema."""

    def up(self, adapter):
        """Run the migration."""
        # Enable pgcrypto extension for UUID generation
        adapter.execute("""
            CREATE EXTENSION IF NOT EXISTS "pgcrypto";
        """)
        print("    ✓ Enabled pgcrypto extension")

        # Create tenants table (master table in PUBLIC schema)
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id VARCHAR(255) UNIQUE NOT NULL,
                organization_name VARCHAR(255) NOT NULL,
                contact_email VARCHAR(320) NOT NULL,
                domain VARCHAR(255) UNIQUE NOT NULL,
                schema_name VARCHAR(255) UNIQUE NOT NULL,
                user_id INTEGER NULL,
                subscriptions JSONB NOT NULL DEFAULT '[]'::jsonb,
                status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                quotas JSONB NOT NULL DEFAULT '{}'::jsonb,
                usage JSONB NOT NULL DEFAULT '{}'::jsonb,
                temp_admin_username VARCHAR(128) NULL,
                temp_admin_password_hash VARCHAR(512) NULL,
                expiry_date TIMESTAMP NULL DEFAULT (NOW() + INTERVAL '365 days'),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
        """)
        print("    ✓ Created tenants table")

        # Create tenant_billing_records table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS tenant_billing_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_uuid UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                amount DECIMAL(15,2) NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'USD',
                billing_period VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                invoice_url VARCHAR(500),
                paid_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
        """)
        print("    ✓ Created tenant_billing_records table")

        # Create tenant_audit_logs table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS tenant_audit_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_uuid UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                user_id INTEGER,
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(100),
                resource_id VARCHAR(255),
                changes JSONB,
                ip_address VARCHAR(50),
                user_agent TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
        """)
        print("    ✓ Created tenant_audit_logs table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS tenant_audit_logs CASCADE;
            DROP TABLE IF EXISTS tenant_billing_records CASCADE;
            DROP TABLE IF EXISTS tenants CASCADE;
        """)
        print("    ✓ Dropped multi-tenant core tables")
