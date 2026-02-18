-- ============================================================================
-- Migration Script: Add phone_number Columns
-- Database: multi_tenant_db
-- ============================================================================
-- This script adds phone_number columns to tenants and tenant_users tables
-- ============================================================================

-- Connect to the multi_tenant_db database
\c multi_tenant_db;

-- Add phone_number column to tenants table
ALTER TABLE tenants
ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20) NULL;

-- Add phone_number column to tenant_users table
ALTER TABLE tenant_users
ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20) NULL;

-- Verification
DO $$
BEGIN
    RAISE NOTICE 'Phone number columns migration completed successfully';
    RAISE NOTICE 'Added phone_number columns to tenants and tenant_users tables';
END $$;
