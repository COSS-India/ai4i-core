-- Model Versioning Migration Script
-- This script migrates the models and services tables to support versioning
-- Run this script on the model_management_db database

\c model_management_db;

-- Step 1: Create version_status enum type
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'version_status') THEN
        CREATE TYPE version_status AS ENUM ('ACTIVE', 'DEPRECATED');
    END IF;
END $$;

-- Step 2: Add new columns to models table
ALTER TABLE models 
    ADD COLUMN IF NOT EXISTS version_status version_status NOT NULL DEFAULT 'ACTIVE',
    ADD COLUMN IF NOT EXISTS version_status_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

-- Step 3: Remove unique constraint on model_id and add composite unique constraint
-- First, drop the existing unique constraint on model_id if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'models_model_id_key' 
        AND conrelid = 'models'::regclass
    ) THEN
        ALTER TABLE models DROP CONSTRAINT models_model_id_key;
    END IF;
END $$;

-- Add composite unique constraint on (model_id, version)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'uq_model_id_version'
    ) THEN
        ALTER TABLE models 
        ADD CONSTRAINT uq_model_id_version UNIQUE (model_id, version);
    END IF;
END $$;

-- Step 4: Add model_version column to services table
ALTER TABLE services 
    ADD COLUMN IF NOT EXISTS model_version VARCHAR(100);

-- Step 5: For existing services, set model_version to the version of the associated model
-- This assumes existing models have a version field
UPDATE services s
SET model_version = m.version
FROM models m
WHERE s.model_id = m.model_id
  AND s.model_version IS NULL;

-- Step 6: Make model_version NOT NULL after populating existing data
-- First check if there are any NULL values
DO $$
DECLARE
    null_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count
    FROM services
    WHERE model_version IS NULL;
    
    IF null_count > 0 THEN
        RAISE EXCEPTION 'Cannot proceed: % services have NULL model_version. Please update them first.', null_count;
    END IF;
END $$;

-- Now make it NOT NULL
ALTER TABLE services 
    ALTER COLUMN model_version SET NOT NULL;

-- Step 7: Create index on (model_id, version) for faster lookups
CREATE INDEX IF NOT EXISTS idx_models_model_id_version ON models(model_id, version);
CREATE INDEX IF NOT EXISTS idx_models_version_status ON models(version_status);
CREATE INDEX IF NOT EXISTS idx_services_model_id_version ON services(model_id, model_version);

-- Step 8: Add comments
COMMENT ON COLUMN models.version_status IS 'Status of the model version: ACTIVE or DEPRECATED';
COMMENT ON COLUMN models.version_status_updated_at IS 'Timestamp when the version status was last updated';
COMMENT ON COLUMN services.model_version IS 'Version of the model associated with this service';
COMMENT ON CONSTRAINT uq_model_id_version ON models IS 'Ensures unique combination of model_id and version';

-- Step 9: Create trigger to update version_status_updated_at when version_status changes
CREATE OR REPLACE FUNCTION update_version_status_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.version_status IS DISTINCT FROM OLD.version_status THEN
        NEW.version_status_updated_at = CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_models_version_status_updated_at ON models;
CREATE TRIGGER update_models_version_status_updated_at
    BEFORE UPDATE ON models
    FOR EACH ROW
    WHEN (NEW.version_status IS DISTINCT FROM OLD.version_status)
    EXECUTE FUNCTION update_version_status_updated_at();

-- Step 10: Set version_status_updated_at for existing records
UPDATE models
SET version_status_updated_at = created_at
WHERE version_status_updated_at IS NULL OR version_status_updated_at < created_at;

COMMENT ON FUNCTION update_version_status_updated_at() IS 'Trigger function to update version_status_updated_at when version_status changes';

