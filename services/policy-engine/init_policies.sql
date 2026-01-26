-- Schema for AI4I Policy Framework
CREATE TABLE IF NOT EXISTS smr_tenant_policies (
    tenant_id VARCHAR(50) PRIMARY KEY,
    latency_policy VARCHAR(20) NOT NULL DEFAULT 'medium', -- low, medium, high
    cost_policy VARCHAR(20) NOT NULL DEFAULT 'tier_2',    -- tier_1, tier_2, tier_3
    accuracy_policy VARCHAR(20) NOT NULL DEFAULT 'standard', -- sensitive, standard
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- SEED DATA (Simulating Adopter Configurations)
-- Tenant A: Critical Healthcare App (Sensitive Accuracy, Low Latency, High Cost allowed)
INSERT INTO smr_tenant_policies (tenant_id, latency_policy, cost_policy, accuracy_policy)
VALUES ('tenant-a', 'low', 'tier_3', 'sensitive')
ON CONFLICT (tenant_id) DO NOTHING;

-- Tenant B: Student App (Lowest Cost, Standard Accuracy, High Latency allowed)
INSERT INTO smr_tenant_policies (tenant_id, latency_policy, cost_policy, accuracy_policy)
VALUES ('tenant-b', 'high', 'tier_1', 'standard')
ON CONFLICT (tenant_id) DO NOTHING;
