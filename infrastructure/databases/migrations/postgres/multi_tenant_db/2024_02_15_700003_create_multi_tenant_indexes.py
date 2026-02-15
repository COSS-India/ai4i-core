from infrastructure.databases.core.base_migration import BaseMigration

class CreateMultiTenantIndexes(BaseMigration):
    """Create indexes for multi-tenant tables in multi_tenant_db."""

    def up(self, adapter):
        """Run the migration."""
        # Indexes for tenants
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_tenants_contact_email ON tenants(contact_email);
            CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
            CREATE INDEX IF NOT EXISTS idx_tenants_created_at ON tenants(created_at);
            CREATE INDEX IF NOT EXISTS idx_tenants_expiry_date ON tenants(expiry_date);
        """)
        print("    ✓ Created indexes for tenants")

        # Indexes for tenant_billing_records
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_tenant_billing_records_tenant_uuid ON tenant_billing_records(tenant_uuid);
            CREATE INDEX IF NOT EXISTS idx_tenant_billing_records_status ON tenant_billing_records(status);
            CREATE INDEX IF NOT EXISTS idx_tenant_billing_records_billing_period ON tenant_billing_records(billing_period);
            CREATE INDEX IF NOT EXISTS idx_tenant_billing_records_created_at ON tenant_billing_records(created_at);
        """)
        print("    ✓ Created indexes for tenant_billing_records")

        # Indexes for tenant_audit_logs
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_tenant_audit_logs_tenant_uuid ON tenant_audit_logs(tenant_uuid);
            CREATE INDEX IF NOT EXISTS idx_tenant_audit_logs_user_id ON tenant_audit_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_tenant_audit_logs_action ON tenant_audit_logs(action);
            CREATE INDEX IF NOT EXISTS idx_tenant_audit_logs_created_at ON tenant_audit_logs(created_at);
        """)
        print("    ✓ Created indexes for tenant_audit_logs")

        # Indexes for tenant_email_verifications
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_tenant_email_verifications_tenant_uuid ON tenant_email_verifications(tenant_uuid);
            CREATE INDEX IF NOT EXISTS idx_tenant_email_verifications_email ON tenant_email_verifications(email);
            CREATE INDEX IF NOT EXISTS idx_tenant_email_verifications_expires_at ON tenant_email_verifications(expires_at);
        """)
        print("    ✓ Created indexes for tenant_email_verifications")

        # Indexes for service_config
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_service_config_is_active ON service_config(is_active);
            CREATE INDEX IF NOT EXISTS idx_service_config_created_at ON service_config(created_at);
        """)
        print("    ✓ Created indexes for service_config")

        # Indexes for tenant_users
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_tenant_users_user_id ON tenant_users(user_id);
            CREATE INDEX IF NOT EXISTS idx_tenant_users_tenant_id ON tenant_users(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_tenant_users_email ON tenant_users(email);
        """)
        print("    ✓ Created indexes for tenant_users")

        # Indexes for user_billing_records
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_billing_records_tenant_user_uuid ON user_billing_records(tenant_user_uuid);
            CREATE INDEX IF NOT EXISTS idx_user_billing_records_status ON user_billing_records(status);
            CREATE INDEX IF NOT EXISTS idx_user_billing_records_billing_period ON user_billing_records(billing_period);
            CREATE INDEX IF NOT EXISTS idx_user_billing_records_created_at ON user_billing_records(created_at);
        """)
        print("    ✓ Created indexes for user_billing_records")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP INDEX IF EXISTS idx_user_billing_records_created_at;
            DROP INDEX IF EXISTS idx_user_billing_records_billing_period;
            DROP INDEX IF EXISTS idx_user_billing_records_status;
            DROP INDEX IF EXISTS idx_user_billing_records_tenant_user_uuid;
            DROP INDEX IF EXISTS idx_tenant_users_email;
            DROP INDEX IF EXISTS idx_tenant_users_tenant_id;
            DROP INDEX IF EXISTS idx_tenant_users_user_id;
            DROP INDEX IF EXISTS idx_service_config_created_at;
            DROP INDEX IF EXISTS idx_service_config_is_active;
            DROP INDEX IF EXISTS idx_tenant_email_verifications_expires_at;
            DROP INDEX IF EXISTS idx_tenant_email_verifications_email;
            DROP INDEX IF EXISTS idx_tenant_email_verifications_tenant_uuid;
            DROP INDEX IF EXISTS idx_tenant_audit_logs_created_at;
            DROP INDEX IF EXISTS idx_tenant_audit_logs_action;
            DROP INDEX IF EXISTS idx_tenant_audit_logs_user_id;
            DROP INDEX IF EXISTS idx_tenant_audit_logs_tenant_uuid;
            DROP INDEX IF EXISTS idx_tenant_billing_records_created_at;
            DROP INDEX IF EXISTS idx_tenant_billing_records_billing_period;
            DROP INDEX IF EXISTS idx_tenant_billing_records_status;
            DROP INDEX IF EXISTS idx_tenant_billing_records_tenant_uuid;
            DROP INDEX IF EXISTS idx_tenants_expiry_date;
            DROP INDEX IF EXISTS idx_tenants_created_at;
            DROP INDEX IF EXISTS idx_tenants_status;
            DROP INDEX IF EXISTS idx_tenants_contact_email;
        """)
        print("    ✓ Dropped multi-tenant indexes")
