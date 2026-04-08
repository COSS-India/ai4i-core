-- =============================================================================
-- Billing / quota / rate-limit / plans v2 — manual PostgreSQL migration
-- =============================================================================
-- Run against the correct database for each section (comments show \c targets).
-- Review and backfill data before enforcing NOT NULL or dropping columns.
-- Idempotent where possible: IF NOT EXISTS / IF EXISTS.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1) Policy engine database
--    Use the DB from your policy-engine DATABASE_URL (often ai4i_platform).
-- -----------------------------------------------------------------------------
-- \c ai4i_platform

-- New table: per-service rows for a quota config (replaces JSONB service_limits on quota_configs)
CREATE TABLE IF NOT EXISTS quota_service_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quota_config_id UUID NOT NULL REFERENCES quota_configs(id) ON DELETE CASCADE,
    service_type VARCHAR(64) NOT NULL,
    unit_type VARCHAR(64) NOT NULL,
    limit_value INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_quota_service_limits_quota_config_id
    ON quota_service_limits (quota_config_id);

-- quota_configs: new shape (name + requests_per_hour; legacy day/month/jsonb/tier removed)
ALTER TABLE quota_configs ADD COLUMN IF NOT EXISTS name VARCHAR(255);
ALTER TABLE quota_configs ADD COLUMN IF NOT EXISTS requests_per_hour INTEGER;

-- Optional backfill if migrating from old columns (uncomment if those columns exist):
-- UPDATE quota_configs
-- SET requests_per_hour = COALESCE(requests_per_hour, requests_per_day, 1000)
-- WHERE requests_per_hour IS NULL;
-- UPDATE quota_configs SET name = COALESCE(name, 'quota-' || id::text) WHERE name IS NULL;

-- After backfill, enforce NOT NULL (will fail until no NULLs):
-- ALTER TABLE quota_configs ALTER COLUMN name SET NOT NULL;
-- ALTER TABLE quota_configs ALTER COLUMN requests_per_hour SET NOT NULL;

-- After backfilling name and requests_per_hour, enforce NOT NULL + defaults as needed, e.g.:
-- ALTER TABLE quota_configs ALTER COLUMN requests_per_hour SET DEFAULT 1000;
-- ALTER TABLE quota_configs ALTER COLUMN requests_per_hour SET NOT NULL;
-- ALTER TABLE quota_configs ALTER COLUMN name SET NOT NULL;

-- Legacy columns to drop once data is migrated into quota_service_limits / new fields:
ALTER TABLE quota_configs DROP COLUMN IF EXISTS tier;
ALTER TABLE quota_configs DROP COLUMN IF EXISTS requests_per_day;
ALTER TABLE quota_configs DROP COLUMN IF EXISTS requests_per_month;
ALTER TABLE quota_configs DROP COLUMN IF EXISTS service_limits;

-- Ensure unique "name" values before creating the index (adjust literals if you prefer real names).
UPDATE quota_configs
SET name = COALESCE(NULLIF(btrim(name), ''), 'quota-' || id::text)
WHERE name IS NULL OR btrim(COALESCE(name, '')) = '';

-- Unique name (drop old name if constraint differs, then add)
ALTER TABLE quota_configs DROP CONSTRAINT IF EXISTS quota_configs_name_key;
ALTER TABLE quota_configs DROP CONSTRAINT IF EXISTS uq_quota_configs_name;
DROP INDEX IF EXISTS uq_quota_configs_name;
CREATE UNIQUE INDEX IF NOT EXISTS uq_quota_configs_name ON quota_configs (name);

-- rate_limit_configs: hourly fields + name; remove tier and per-second limits
ALTER TABLE rate_limit_configs ADD COLUMN IF NOT EXISTS name VARCHAR(255);
ALTER TABLE rate_limit_configs ADD COLUMN IF NOT EXISTS requests_per_hour_per_api_key INTEGER;
ALTER TABLE rate_limit_configs ADD COLUMN IF NOT EXISTS requests_per_hour_per_tenant INTEGER;

-- Optional backfill from legacy RPS (example: multiply by 3600 — adjust to your policy):
-- UPDATE rate_limit_configs SET
--   requests_per_hour_per_api_key = COALESCE(requests_per_hour_per_api_key, (requests_per_sec_per_api_key * 3600)::int, 200),
--   requests_per_hour_per_tenant = COALESCE(requests_per_hour_per_tenant, (requests_per_sec_per_tenant * 3600)::int, 1000)
-- WHERE requests_per_hour_per_api_key IS NULL OR requests_per_hour_per_tenant IS NULL;

UPDATE rate_limit_configs SET requests_per_hour_per_api_key = 200 WHERE requests_per_hour_per_api_key IS NULL;
UPDATE rate_limit_configs SET requests_per_hour_per_tenant = 1000 WHERE requests_per_hour_per_tenant IS NULL;

ALTER TABLE rate_limit_configs
    ALTER COLUMN requests_per_hour_per_api_key SET DEFAULT 200;
ALTER TABLE rate_limit_configs
    ALTER COLUMN requests_per_hour_per_tenant SET DEFAULT 1000;

-- Fails if any row still has NULL (backfill from legacy RPS columns first if needed).
ALTER TABLE rate_limit_configs ALTER COLUMN requests_per_hour_per_api_key SET NOT NULL;
ALTER TABLE rate_limit_configs ALTER COLUMN requests_per_hour_per_tenant SET NOT NULL;

-- Backfill display name before unique index (uses tier only if column still exists — idempotent re-runs).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'rate_limit_configs' AND column_name = 'tier'
    ) THEN
        EXECUTE $u$
            UPDATE rate_limit_configs
            SET name = COALESCE(
                NULLIF(btrim(name), ''),
                CASE WHEN tier IS NOT NULL AND btrim(tier) <> '' THEN btrim(tier) || '-' || id::text ELSE 'rl-' || id::text END
            )
            WHERE name IS NULL OR btrim(COALESCE(name, '')) = ''
        $u$;
    ELSE
        EXECUTE $u$
            UPDATE rate_limit_configs
            SET name = COALESCE(NULLIF(btrim(name), ''), 'rl-' || id::text)
            WHERE name IS NULL OR btrim(COALESCE(name, '')) = ''
        $u$;
    END IF;
END $$;

ALTER TABLE rate_limit_configs DROP COLUMN IF EXISTS tier;
ALTER TABLE rate_limit_configs DROP COLUMN IF EXISTS requests_per_sec_per_api_key;
ALTER TABLE rate_limit_configs DROP COLUMN IF EXISTS requests_per_sec_per_tenant;

ALTER TABLE rate_limit_configs DROP CONSTRAINT IF EXISTS rate_limit_configs_name_key;
ALTER TABLE rate_limit_configs DROP CONSTRAINT IF EXISTS uq_rate_limit_configs_name;
DROP INDEX IF EXISTS uq_rate_limit_configs_name;
CREATE UNIQUE INDEX IF NOT EXISTS uq_rate_limit_configs_name ON rate_limit_configs (name);

-- subscription_plans: plan_name, cost, FKs; drop allowed_service_ids / legacy name
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS plan_name VARCHAR(128);
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS cost NUMERIC(12, 2) DEFAULT 100.00;
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS quota_config_id UUID;
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS rate_limit_config_id UUID;

-- Copy legacy "name" into plan_name when present
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_plans' AND column_name = 'name'
    ) THEN
        EXECUTE $u$
            UPDATE subscription_plans SET plan_name = COALESCE(plan_name, name)
            WHERE plan_name IS NULL OR plan_name = ''
        $u$;
    END IF;
END $$;

UPDATE subscription_plans SET cost = 100.00 WHERE cost IS NULL;

UPDATE subscription_plans
SET plan_name = COALESCE(NULLIF(btrim(plan_name), ''), 'plan-' || id::text)
WHERE plan_name IS NULL OR btrim(COALESCE(plan_name, '')) = '';

-- Add FKs (nullable until you assign ids)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'subscription_plans_quota_config_id_fkey'
    ) THEN
        ALTER TABLE subscription_plans
            ADD CONSTRAINT subscription_plans_quota_config_id_fkey
            FOREIGN KEY (quota_config_id) REFERENCES quota_configs(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'subscription_plans_rate_limit_config_id_fkey'
    ) THEN
        ALTER TABLE subscription_plans
            ADD CONSTRAINT subscription_plans_rate_limit_config_id_fkey
            FOREIGN KEY (rate_limit_config_id) REFERENCES rate_limit_configs(id);
    END IF;
END $$;

ALTER TABLE subscription_plans DROP COLUMN IF EXISTS allowed_service_ids;
ALTER TABLE subscription_plans DROP COLUMN IF EXISTS name;

-- Enforce NOT NULL on plan_name / cost / FKs only after backfilling rows:
-- ALTER TABLE subscription_plans ALTER COLUMN plan_name SET NOT NULL;
-- ALTER TABLE subscription_plans ALTER COLUMN cost SET NOT NULL;
-- ALTER TABLE subscription_plans ALTER COLUMN quota_config_id SET NOT NULL;
-- ALTER TABLE subscription_plans ALTER COLUMN rate_limit_config_id SET NOT NULL;

ALTER TABLE subscription_plans DROP CONSTRAINT IF EXISTS uq_subscription_plans_plan_name;
ALTER TABLE subscription_plans DROP CONSTRAINT IF EXISTS uq_subscription_plans_tier;
DROP INDEX IF EXISTS uq_subscription_plans_plan_name;
DROP INDEX IF EXISTS uq_subscription_plans_tier;
CREATE UNIQUE INDEX IF NOT EXISTS uq_subscription_plans_plan_name ON subscription_plans (plan_name);
CREATE UNIQUE INDEX IF NOT EXISTS uq_subscription_plans_tier ON subscription_plans (tier);


-- -----------------------------------------------------------------------------
-- 2) Pay-per-use database (pay_per_use_db)
-- -----------------------------------------------------------------------------
-- \c pay_per_use_db

ALTER TABLE wallet_balances ADD COLUMN IF NOT EXISTS total_plan_cost NUMERIC(20, 6) NOT NULL DEFAULT 0;
ALTER TABLE wallet_balances ADD COLUMN IF NOT EXISTS total_used NUMERIC(20, 6) NOT NULL DEFAULT 0;

ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS rate_used NUMERIC(20, 8);
ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS tier VARCHAR(32);


-- -----------------------------------------------------------------------------
-- 3) Multi-tenant database (multi_tenant_db)
-- -----------------------------------------------------------------------------
-- \c multi_tenant_db

ALTER TABLE tenant_plans ADD COLUMN IF NOT EXISTS plan_cost NUMERIC(12, 2);

-- =============================================================================
-- End
-- =============================================================================
