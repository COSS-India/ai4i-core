-- Manual rollout for pay-per-use and tenant plan features.
-- Run as superuser or DB owner. Adjust connection if needed.
--
-- 1) Create dedicated database (skip if it exists — use one of the patterns below).
--    From psql connected to postgres:
--      CREATE DATABASE pay_per_use_db OWNER current_user;
--
-- 2) multi_tenant_db: new columns + tenant_plans
\c multi_tenant_db

ALTER TABLE service_config ADD COLUMN IF NOT EXISTS cost_per_unit NUMERIC(10, 4);
ALTER TABLE service_config ADD COLUMN IF NOT EXISTS tier VARCHAR(20);
ALTER TABLE service_config ADD COLUMN IF NOT EXISTS billing_unit_type VARCHAR(32);

CREATE TABLE IF NOT EXISTS tenant_plans (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL,
    plan_name VARCHAR(128) NOT NULL,
    tier VARCHAR(32) NOT NULL,
    quota_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    rate_limit_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    allowed_services JSONB NOT NULL DEFAULT '[]'::jsonb,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_tenant_plans_tenant_id ON tenant_plans (tenant_id);
CREATE INDEX IF NOT EXISTS ix_tenant_plans_plan_id ON tenant_plans (plan_id);
CREATE INDEX IF NOT EXISTS ix_service_config_tier ON service_config (tier);

-- 3) model_management_db: pricing fields on services
\c model_management_db

ALTER TABLE services ADD COLUMN IF NOT EXISTS cost_per_unit NUMERIC(10, 4);
ALTER TABLE services ADD COLUMN IF NOT EXISTS billing_unit_type VARCHAR(32);
ALTER TABLE services ADD COLUMN IF NOT EXISTS tier VARCHAR(20);
