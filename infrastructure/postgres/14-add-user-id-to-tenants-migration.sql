-- ============================================================================
-- Migration: Add user_id column to tenants table
-- ============================================================================
-- This migration adds the user_id column to the tenants table in multi_tenant_db.
-- The column was defined in the schema but may be missing in existing databases.
--
-- Run this script using:
--   docker compose exec postgres psql -U ${POSTGRES_USER} -d multi_tenant_db -f /docker-entrypoint-initdb.d/14-add-user-id-to-tenants-migration.sql
-- ============================================================================

\c multi_tenant_db;

-- ============================================================================
-- Add user_id column to tenants table
-- ============================================================================
DO $$
BEGIN
    -- Add user_id column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'tenants' 
        AND column_name = 'user_id'
    ) THEN
        ALTER TABLE tenants ADD COLUMN user_id INTEGER NULL;
        RAISE NOTICE 'Added user_id column to tenants table';
    ELSE
        RAISE NOTICE 'user_id column already exists in tenants table';
    END IF;
END $$;

-- Create index for user_id if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_tenants_user_id ON tenants(user_id);

-- Add comment to document the column
COMMENT ON COLUMN tenants.user_id IS 'References users.id in auth_db - nullable for tenants created before user association';

-- ============================================================================
-- Migration complete
-- ============================================================================
SELECT 'Migration 14-add-user-id-to-tenants completed successfully' as status;
