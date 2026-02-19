from infrastructure.databases.core.base_migration import BaseMigration

class CreateMultiTenantAdditionalTables(BaseMigration):
    """Create additional multi-tenant tables (tenant_email_verifications, service_config, tenant_users, user_billing_records) in multi_tenant_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create tenant_email_verifications table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS tenant_email_verifications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_uuid UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                email VARCHAR(320) NOT NULL,
                verification_token VARCHAR(255) UNIQUE NOT NULL,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                verified_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
        """)
        print("    ✓ Created tenant_email_verifications table")

        # Create service_config table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS service_config (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                service_name VARCHAR(100) UNIQUE NOT NULL,
                display_name VARCHAR(255) NOT NULL,
                description TEXT,
                base_price DECIMAL(15,2) NOT NULL DEFAULT 0.00,
                pricing_model VARCHAR(50) NOT NULL DEFAULT 'PAY_PER_USE',
                features JSONB NOT NULL DEFAULT '{}'::jsonb,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
        """)
        print("    ✓ Created service_config table")

        # Create tenant_users table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS tenant_users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER NOT NULL,
                tenant_uuid UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
                username VARCHAR(255) NOT NULL,
                email VARCHAR(320) NOT NULL,
                subscriptions JSONB NOT NULL DEFAULT '[]'::jsonb,
                is_approved BOOLEAN NOT NULL DEFAULT FALSE,
                status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
        """)
        print("    ✓ Created tenant_users table")

        # Create user_billing_records table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS user_billing_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_user_uuid UUID NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
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
        print("    ✓ Created user_billing_records table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS user_billing_records CASCADE;
            DROP TABLE IF EXISTS tenant_users CASCADE;
            DROP TABLE IF EXISTS service_config CASCADE;
            DROP TABLE IF EXISTS tenant_email_verifications CASCADE;
        """)
        print("    ✓ Dropped additional multi-tenant tables")
