-- ============================================================================
-- Multi-Tenant Database Schema Initialization Script
-- Database: multi_tenant_db
-- ============================================================================
-- This script creates all tables for the multi-tenant feature
-- All tables are created in the 'public' schema unless otherwise specified
-- 
-- NOTE: Enum values are stored as VARCHAR columns (not PostgreSQL ENUMs)
-- because SQLAlchemy models use native_enum=False, create_type=False
-- Validation is handled at the application level in Python
-- ============================================================================

-- Connect to the multi_tenant_db database
\c multi_tenant_db;

-- ============================================================================
-- STEP 1: Create Tables
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Table: tenants
-- Description: Master tenants table (stored in public schema)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) UNIQUE NOT NULL,
    organization_name VARCHAR(255) NOT NULL,
    contact_email VARCHAR(320) NOT NULL,
    domain VARCHAR(255) UNIQUE NOT NULL,
    schema_name VARCHAR(255) UNIQUE NOT NULL,
    user_id INTEGER NULL,
    subscriptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    quotas JSONB NOT NULL DEFAULT '{}'::jsonb,
    usage JSONB NOT NULL DEFAULT '{}'::jsonb,
    temp_admin_username VARCHAR(128) NULL,
    temp_admin_password_hash VARCHAR(512) NULL,
    expiry_date TIMESTAMP NULL DEFAULT (NOW() + INTERVAL '365 days'),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for tenants table
CREATE INDEX IF NOT EXISTS idx_tenants_contact_email ON tenants(contact_email);
CREATE INDEX IF NOT EXISTS idx_tenants_user_id ON tenants(user_id);

-- ----------------------------------------------------------------------------
-- Table: tenant_billing_records
-- Description: Billing records for tenants
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_billing_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    billing_customer_id VARCHAR(255) NULL,
    cost NUMERIC(20, 10) NOT NULL DEFAULT 0.00,
    billing_status VARCHAR(50) NOT NULL DEFAULT 'UNPAID',
    suspension_reason VARCHAR(512) NULL,
    suspended_until TIMESTAMP NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_tenant_billing_records_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(id) 
        ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- Table: tenant_audit_logs
-- Description: Audit logs for tenant actions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    actor VARCHAR(50) NOT NULL DEFAULT 'system',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_tenant_audit_logs_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(id) 
        ON DELETE CASCADE
);

-- Indexes for tenant_audit_logs table
CREATE INDEX IF NOT EXISTS idx_tenant_audit_logs_tenant_id ON tenant_audit_logs(tenant_id);

-- ----------------------------------------------------------------------------
-- Table: tenant_email_verifications
-- Description: Email verification tokens for tenants
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_email_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    token VARCHAR(512) UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    verified_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_tenant_email_verifications_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(id) 
        ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- Table: service_config
-- Description: Service configuration and pricing
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_config (
    id BIGSERIAL PRIMARY KEY,
    service_name VARCHAR(50) UNIQUE NOT NULL,
    unit_type VARCHAR(50) NOT NULL,
    price_per_unit NUMERIC(10, 6) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- Table: tenant_users
-- Description: Users associated with tenants
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    tenant_uuid UUID NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(320) NOT NULL,
    subscriptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_tenant_users_tenant_uuid 
        FOREIGN KEY (tenant_uuid) 
        REFERENCES tenants(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_tenant_users_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(tenant_id) 
        ON DELETE CASCADE
);

-- Indexes for tenant_users table
CREATE INDEX IF NOT EXISTS idx_tenant_users_user_id ON tenant_users(user_id);
CREATE INDEX IF NOT EXISTS idx_tenant_users_tenant_id ON tenant_users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_users_email ON tenant_users(email);

-- ----------------------------------------------------------------------------
-- Table: user_billing_records
-- Description: Billing records for individual tenant users
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_billing_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    service_name VARCHAR(50) NOT NULL,
    service_id BIGINT NOT NULL,
    cost NUMERIC(20, 10) NOT NULL DEFAULT 0.00,
    billing_period DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_user_billing_records_user_id 
        FOREIGN KEY (user_id) 
        REFERENCES tenant_users(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_user_billing_records_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(tenant_id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_user_billing_records_service_id 
        FOREIGN KEY (service_id) 
        REFERENCES service_config(id)
);

-- ============================================================================
-- STEP 2: Create Triggers for updated_at Timestamps
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to all tables with updated_at column
CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tenant_billing_records_updated_at
    BEFORE UPDATE ON tenant_billing_records
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tenant_audit_logs_updated_at
    BEFORE UPDATE ON tenant_audit_logs
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

-- ============================================================================
-- STEP 3: Add Comments for Documentation
-- ============================================================================

COMMENT ON TABLE tenants IS 'Master tenants table storing tenant information in public schema';
COMMENT ON COLUMN tenants.tenant_id IS 'User-provided unique tenant identifier';
COMMENT ON COLUMN tenants.schema_name IS 'Generated database schema name for tenant-specific tables';
COMMENT ON COLUMN tenants.subscriptions IS 'Array of service names the tenant is subscribed to (e.g., ["tts", "asr", "nmt"])';
COMMENT ON COLUMN tenants.quotas IS 'JSON object with quota limits (e.g., {"api_calls_per_day": 10000, "storage_gb": 10})';
COMMENT ON COLUMN tenants.usage IS 'JSON object with current usage metrics (e.g., {"api_calls_today": 500, "storage_used_gb": 2.5})';

COMMENT ON TABLE tenant_billing_records IS 'Billing records for tenant-level billing';
COMMENT ON TABLE tenant_audit_logs IS 'Audit trail of all tenant-related actions';
COMMENT ON TABLE tenant_email_verifications IS 'Email verification tokens for tenant registration';
COMMENT ON TABLE service_config IS 'Service configuration and pricing information';
COMMENT ON TABLE tenant_users IS 'Users associated with tenants (many-to-one relationship)';
COMMENT ON TABLE user_billing_records IS 'Billing records for individual tenant users';

-- ============================================================================
-- STEP 4: Verification
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Multi-tenant database schema initialization completed successfully';
    RAISE NOTICE 'Created tables: tenants, tenant_billing_records, tenant_audit_logs, tenant_email_verifications, service_config, tenant_users, user_billing_records';
    RAISE NOTICE 'All tables are in the public schema of multi_tenant_db database';
END $$;
