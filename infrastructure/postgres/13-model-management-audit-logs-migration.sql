-- ============================================================================
-- Migration: Add created_by and updated_by columns to models and services
-- ============================================================================
-- This migration adds user tracking columns to track who created/updated
-- models and services.
--
-- Run this script using:
--   docker compose exec postgres psql -U dhruva_user -d model_management_db -f /docker-entrypoint-initdb.d/13-model-management-audit-logs-migration.sql
-- ============================================================================

-- \c model_management_db;

-- ============================================================================
-- Add created_by and updated_by columns to models table
-- ============================================================================
DO $$
BEGIN
    -- Add created_by column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'models' 
        AND column_name = 'created_by'
    ) THEN
        ALTER TABLE models ADD COLUMN created_by VARCHAR(255) DEFAULT NULL;
        -- RAISE NOTICE 'Added created_by column to models table';
    END IF;

    -- Add updated_by column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'models' 
        AND column_name = 'updated_by'
    ) THEN
        ALTER TABLE models ADD COLUMN updated_by VARCHAR(255) DEFAULT NULL;
        -- RAISE NOTICE 'Added updated_by column to models table';
    END IF;
END $$;

-- Add comments to document the columns
COMMENT ON COLUMN models.created_by IS 'User ID (string) who created this model';
COMMENT ON COLUMN models.updated_by IS 'User ID (string) who last updated this model';

-- Create index for filtering by created_by
CREATE INDEX IF NOT EXISTS idx_models_created_by ON models(created_by);

-- ============================================================================
-- Add created_by and updated_by columns to services table
-- ============================================================================
DO $$
BEGIN
    -- Add created_by column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'services' 
        AND column_name = 'created_by'
    ) THEN
        ALTER TABLE services ADD COLUMN created_by VARCHAR(255) DEFAULT NULL;
        -- RAISE NOTICE 'Added created_by column to services table';
    END IF;

    -- Add updated_by column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'services' 
        AND column_name = 'updated_by'
    ) THEN
        ALTER TABLE services ADD COLUMN updated_by VARCHAR(255) DEFAULT NULL;
        -- RAISE NOTICE 'Added updated_by column to services table';
    END IF;
END $$;

-- Add comments to document the columns
COMMENT ON COLUMN services.created_by IS 'User ID (string) who created this service';
COMMENT ON COLUMN services.updated_by IS 'User ID (string) who last updated this service';

-- Create index for filtering by created_by
CREATE INDEX IF NOT EXISTS idx_services_created_by ON services(created_by);

-- ============================================================================
-- Migration complete
-- ============================================================================
-- RAISE NOTICE 'Migration 13-created-updated-by-migration completed successfully';
