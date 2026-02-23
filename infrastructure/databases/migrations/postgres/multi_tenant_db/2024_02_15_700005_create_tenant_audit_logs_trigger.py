"""
Create Tenant Audit Logs Trigger Migration
Adds updated_at trigger for tenant_audit_logs table
"""
from infrastructure.databases.core.base_migration import BaseMigration


class CreateTenantAuditLogsTrigger(BaseMigration):
    """Create updated_at trigger for tenant_audit_logs"""
    
    def up(self, adapter):
        """Run migration"""
        print("    Creating tenant_audit_logs updated_at trigger...")
        
        adapter.execute("""
            DROP TRIGGER IF EXISTS update_tenant_audit_logs_updated_at ON tenant_audit_logs;
            CREATE TRIGGER update_tenant_audit_logs_updated_at
                BEFORE UPDATE ON tenant_audit_logs
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
        print("    ✓ Created update_tenant_audit_logs_updated_at trigger")
        
    def down(self, adapter):
        """Rollback migration"""
        print("    Dropping tenant_audit_logs updated_at trigger...")
        
        adapter.execute("""
            DROP TRIGGER IF EXISTS update_tenant_audit_logs_updated_at ON tenant_audit_logs;
        """)
        print("    ✓ Dropped update_tenant_audit_logs_updated_at trigger")
