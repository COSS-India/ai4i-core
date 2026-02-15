from infrastructure.databases.core.base_seeder import BaseSeeder


class PolicyEngineDefaultPoliciesSeeder(BaseSeeder):
    """Seed default tenant policies for policy engine."""
    
    database = 'dhruva_platform'  # Target database
    
    def run(self, adapter):
        """Seed the database."""
        # Check if policies already exist
        result = adapter.execute("""
            SELECT COUNT(*) FROM smr_tenant_policies;
        """, fetch=True)
        
        count = result[0][0] if result else 0
        
        if count > 0:
            print("    ⚠ Policies already exist, skipping seeding")
            return

        # Insert default tenant policies
        adapter.execute("""
            -- Tenant A: Critical Healthcare App (Sensitive Accuracy, Low Latency, High Cost allowed)
            INSERT INTO smr_tenant_policies (tenant_id, latency_policy, cost_policy, accuracy_policy)
            VALUES ('tenant-a', 'low', 'tier_3', 'sensitive')
            ON CONFLICT (tenant_id) DO NOTHING;

            -- Tenant B: Student App (Lowest Cost, Standard Accuracy, High Latency allowed)
            INSERT INTO smr_tenant_policies (tenant_id, latency_policy, cost_policy, accuracy_policy)
            VALUES ('tenant-b', 'high', 'tier_1', 'standard')
            ON CONFLICT (tenant_id) DO NOTHING;

            -- Tenant C: Enterprise App (Balanced - Medium Latency, Tier 2 Cost, Standard Accuracy)
            INSERT INTO smr_tenant_policies (tenant_id, latency_policy, cost_policy, accuracy_policy)
            VALUES ('tenant-c', 'medium', 'tier_2', 'standard')
            ON CONFLICT (tenant_id) DO NOTHING;
        """)
        
        print("    ✓ Seeded default tenant policies (tenant-a, tenant-b, tenant-c)")
