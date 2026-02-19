from infrastructure.databases.core.base_migration import BaseMigration

class CreateMultiTenantFunctions(BaseMigration):
    """Create functions and triggers for multi-tenant management in multi_tenant_db.
    
    NOTE: This migration only creates base tables in PUBLIC schema.
    Tenant-specific schemas (e.g., tenant_acme_5d448a) are created dynamically
    at runtime by the application when a tenant is provisioned.
    See: services/multi-tenant-feature/services/tenant_service.py -> provision_tenant_schema()
    """

    def up(self, adapter):
        """Run the migration."""
        # Create updated_at trigger function
        adapter.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        print("    ✓ Created update_updated_at_column function")

        # Create triggers for updated_at columns
        adapter.execute("""
            CREATE TRIGGER update_tenants_updated_at
                BEFORE UPDATE ON tenants
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();

            CREATE TRIGGER update_tenant_billing_records_updated_at
                BEFORE UPDATE ON tenant_billing_records
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();

            CREATE TRIGGER update_service_config_updated_at
                BEFORE UPDATE ON service_config
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();

            CREATE TRIGGER update_tenant_users_updated_at
                BEFORE UPDATE ON tenant_users
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();

            CREATE TRIGGER update_user_billing_records_updated_at
                BEFORE UPDATE ON user_billing_records
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        """)
        print("    ✓ Created updated_at triggers")
        print("    ⚠️  NOTE: Tenant-specific schemas are created dynamically at runtime")
        print("    ⚠️  See: services/multi-tenant-feature/services/tenant_service.py")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TRIGGER IF EXISTS update_user_billing_records_updated_at ON user_billing_records;
            DROP TRIGGER IF EXISTS update_tenant_users_updated_at ON tenant_users;
            DROP TRIGGER IF EXISTS update_service_config_updated_at ON service_config;
            DROP TRIGGER IF EXISTS update_tenant_billing_records_updated_at ON tenant_billing_records;
            DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants;
            DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;
        """)
        print("    ✓ Dropped multi-tenant functions and triggers")
