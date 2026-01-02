-- Model Versioning Migration Rollback Script
-- This script reverts all changes made by 10-model-versioning-migration.sql
-- Run this script on the model_management_db database to rollback model versioning changes
-- WARNING: This will remove all versioning-related columns and constraints
-- Also restores publish/unpublish columns to models table (and removes from services)

-- !!ROLLBACK SCRIPT!!

\c model_management_db;

-- Step 1: Drop trigger and trigger function
DROP TRIGGER IF EXISTS update_models_version_status_updated_at ON models;
DROP FUNCTION IF EXISTS update_version_status_updated_at();

-- Step 2: Remove comments
COMMENT ON COLUMN models.version_status IS NULL;
COMMENT ON COLUMN models.version_status_updated_at IS NULL;
COMMENT ON COLUMN services.model_version IS NULL;
COMMENT ON CONSTRAINT uq_model_id_version ON models IS NULL;
COMMENT ON FUNCTION update_version_status_updated_at() IS NULL;

-- Step 3: Drop indexes created by the migration
DROP INDEX IF EXISTS idx_models_model_id_version;
DROP INDEX IF EXISTS idx_models_version_status;
DROP INDEX IF EXISTS idx_services_model_id_version;

-- Step 4: Drop the composite foreign key constraint first (before dropping model_version column)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'services_model_id_fkey' 
        AND conrelid = 'services'::regclass
    ) THEN
        ALTER TABLE services DROP CONSTRAINT services_model_id_fkey;
    END IF;
END $$;

-- Step 5: Make model_version nullable (remove NOT NULL constraint)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'services' 
        AND column_name = 'model_version'
        AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE services 
        ALTER COLUMN model_version DROP NOT NULL;
    END IF;
END $$;

-- Step 6: Drop model_version column from services table
ALTER TABLE services 
    DROP COLUMN IF EXISTS model_version;

-- Step 7: Restore unique constraint on model_id (drop composite, add back single)
-- Drop the composite unique constraint
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'uq_model_id_version'
    ) THEN
        ALTER TABLE models DROP CONSTRAINT uq_model_id_version;
    END IF;
END $$;

-- Add back the original unique constraint on model_id
-- Note: This assumes model_id should be unique. If your original schema didn't have this,
-- you may need to comment out or modify this section
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'models_model_id_key' 
        AND conrelid = 'models'::regclass
    ) THEN
        ALTER TABLE models 
        ADD CONSTRAINT models_model_id_key UNIQUE (model_id);
    END IF;
END $$;

-- Re-add the foreign key constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'services_model_id_fkey' 
        AND conrelid = 'services'::regclass
    ) THEN
        ALTER TABLE services 
        ADD CONSTRAINT services_model_id_fkey 
        FOREIGN KEY (model_id) REFERENCES models(model_id);
    END IF;
END $$;

-- Step 8: Restore updated_on NOT NULL constraint
-- First set any NULL values to current timestamp to avoid constraint violation
UPDATE models SET updated_on = EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT WHERE updated_on IS NULL;
ALTER TABLE models ALTER COLUMN updated_on SET NOT NULL;

-- Step 9: Drop versioning columns from models table
ALTER TABLE models 
    DROP COLUMN IF EXISTS version_status_updated_at,
    DROP COLUMN IF EXISTS version_status;

-- Step 10: Drop version_status enum type
-- Note: We can only drop the enum if no columns are using it
-- Since we've already dropped the column, we can drop the type
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'version_status') THEN
        DROP TYPE version_status;
    END IF;
END $$;

-- ============================================================================
-- Step 11: Restore publish/unpublish columns to MODELS table
-- (Rollback of moving publish feature to services only)
-- ============================================================================

-- Drop index on services.is_published
DROP INDEX IF EXISTS idx_services_is_published;

-- Remove comments from services publish columns
COMMENT ON COLUMN services.is_published IS NULL;
COMMENT ON COLUMN services.published_at IS NULL;
COMMENT ON COLUMN services.unpublished_at IS NULL;

-- Remove publish-related columns from services table
ALTER TABLE services 
    DROP COLUMN IF EXISTS is_published,
    DROP COLUMN IF EXISTS published_at,
    DROP COLUMN IF EXISTS unpublished_at;

-- Restore publish-related columns to models table
ALTER TABLE models 
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS published_at BIGINT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS unpublished_at BIGINT DEFAULT NULL;

-- Rollback complete
-- The database should now be in the state before the versioning migration

