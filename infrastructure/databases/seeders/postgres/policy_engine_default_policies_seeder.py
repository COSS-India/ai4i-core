from infrastructure.databases.core.base_seeder import BaseSeeder


class PolicyEngineDefaultPoliciesSeeder(BaseSeeder):
    """Seed default tenant policies for policy engine."""
    
    database = 'dhruva_platform'  # Target database
    
    def run(self, adapter):
        """Seed the database."""
        # Check if policies already exist
        row = adapter.fetch_one("SELECT COUNT(*) FROM smr_tenant_policies")
        count = row[0] if row else 0

        if count > 0:
            print("    ⚠ Policies already exist, skipping seeding")
            return

        # Insert default tenant policies (run each INSERT so execute() works)
        for tenant_id, latency, cost, accuracy in [
            ('tenant-a', 'low', 'tier_3', 'sensitive'),
            ('tenant-b', 'high', 'tier_1', 'standard'),
            ('tenant-c', 'medium', 'tier_2', 'standard'),
        ]:
            adapter.execute("""
                INSERT INTO smr_tenant_policies (tenant_id, latency_policy, cost_policy, accuracy_policy)
                VALUES (:tenant_id, :latency, :cost, :accuracy)
                ON CONFLICT (tenant_id) DO NOTHING
            """, {'tenant_id': tenant_id, 'latency': latency, 'cost': cost, 'accuracy': accuracy})

        print("    ✓ Seeded default tenant policies (tenant-a, tenant-b, tenant-c)")
