from infrastructure.databases.core.base_migration import BaseMigration


class CreatePolicyEngineTable(BaseMigration):
    """Create smr_tenant_policies table in main dhruva_platform database for policy engine."""

    def up(self, adapter):
        """Run the migration."""
        adapter.execute("""
            -- Schema for AI4I Policy Framework (Smart Model Routing)
            CREATE TABLE IF NOT EXISTS smr_tenant_policies (
                tenant_id VARCHAR(50) PRIMARY KEY,
                latency_policy VARCHAR(20) NOT NULL DEFAULT 'medium', 
                    -- Allowed values: low, medium, high
                cost_policy VARCHAR(20) NOT NULL DEFAULT 'tier_2',    
                    -- Allowed values: tier_1, tier_2, tier_3
                accuracy_policy VARCHAR(20) NOT NULL DEFAULT 'standard', 
                    -- Allowed values: sensitive, standard
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Create indexes for policy lookups
            CREATE INDEX IF NOT EXISTS idx_smr_tenant_policies_latency 
                ON smr_tenant_policies(latency_policy);
            CREATE INDEX IF NOT EXISTS idx_smr_tenant_policies_cost 
                ON smr_tenant_policies(cost_policy);
            CREATE INDEX IF NOT EXISTS idx_smr_tenant_policies_accuracy 
                ON smr_tenant_policies(accuracy_policy);

            -- Add comments for documentation
            COMMENT ON TABLE smr_tenant_policies IS 'Smart Model Routing (SMR) policies for tenant-specific routing decisions';
            COMMENT ON COLUMN smr_tenant_policies.latency_policy IS 'Latency preference: low (fast), medium (balanced), high (can wait)';
            COMMENT ON COLUMN smr_tenant_policies.cost_policy IS 'Cost preference: tier_1 (cheapest), tier_2 (moderate), tier_3 (premium)';
            COMMENT ON COLUMN smr_tenant_policies.accuracy_policy IS 'Accuracy preference: standard (general use), sensitive (critical applications)';
        """)
        print("    ✓ Created smr_tenant_policies table for policy engine")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS smr_tenant_policies CASCADE;
        """)
        print("    ✓ Dropped smr_tenant_policies table")
