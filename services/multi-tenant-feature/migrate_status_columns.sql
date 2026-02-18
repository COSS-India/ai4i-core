-- ============================================================================
-- Migration Script: Alter Status Columns to VARCHAR(50)
-- Database: multi_tenant_db
-- ============================================================================
-- This script alters status columns to VARCHAR(50) to accommodate longer status values
-- like "DEACTIVATED" (10 characters)
-- ============================================================================
-- Run this script with:
-- docker compose exec -T postgres psql -U dhruva_user -d multi_tenant_db -f /path/to/migrate_status_columns.sql
-- OR execute each ALTER TABLE statement individually
-- ============================================================================

-- Alter tenants.status column
ALTER TABLE tenants
ALTER COLUMN status TYPE VARCHAR(50);

-- Alter tenant_users.status column
ALTER TABLE tenant_users
ALTER COLUMN status TYPE VARCHAR(50);

-- Alter user_billing_records.status column
ALTER TABLE user_billing_records
ALTER COLUMN status TYPE VARCHAR(50);

-- Alter tenant_billing_records.billing_status column
ALTER TABLE tenant_billing_records
ALTER COLUMN billing_status TYPE VARCHAR(50);

-- Verification
DO $$
BEGIN
    RAISE NOTICE 'Status columns migration completed successfully';
    RAISE NOTICE 'All status columns are now VARCHAR(50)';
END $$;
