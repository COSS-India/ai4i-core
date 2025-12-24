-- Migration script to add model versioning support
-- Run this script against the model_management_db database
-- This migration adds version management fields and updates constraints

BEGIN;

-- Step 1: Remove unique constraint from model_id (if exists)
-- Note: This may fail if constraint doesn't exist, which is okay
ALTER TABLE models DROP CONSTRAINT IF EXISTS models_model_id_key;

-- Step 2: Add new version management columns to models table
ALTER TABLE models 
ADD COLUMN IF NOT EXISTS version_status VARCHAR(50) NOT NULL DEFAULT 'active',
ADD COLUMN IF NOT EXISTS release_notes TEXT,
ADD COLUMN IF NOT EXISTS is_immutable BOOLEAN NOT NULL DEFAULT FALSE;

-- Step 3: Add composite unique constraint on (model_id, version)
-- This ensures version uniqueness per model
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_model_id_version'
    ) THEN
        ALTER TABLE models 
        ADD CONSTRAINT uq_model_id_version UNIQUE (model_id, version);
    END IF;
END $$;

-- Step 4: Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_model_id_version ON models (model_id, version);
CREATE INDEX IF NOT EXISTS idx_model_id_version_status ON models (model_id, version_status);

-- Step 5: Update existing records to have default version_status
UPDATE models SET version_status = 'active' WHERE version_status IS NULL;

-- Step 6: Add model_version column to services table
ALTER TABLE services 
ADD COLUMN IF NOT EXISTS model_version VARCHAR(100) NOT NULL DEFAULT '1.0.0',
ADD COLUMN IF NOT EXISTS version_updated_at BIGINT;

-- Step 7: Migrate existing service data
-- For existing services, set model_version to the version of their associated model
-- This assumes existing models have a version field
UPDATE services s
SET model_version = (
    SELECT m.version 
    FROM models m 
    WHERE m.model_id = s.model_id 
    LIMIT 1
)
WHERE s.model_version = '1.0.0' OR s.model_version IS NULL;

-- Step 8: Make model_version NOT NULL after migration
-- First, ensure all services have a valid model_version
UPDATE services 
SET model_version = '1.0.0' 
WHERE model_version IS NULL OR model_version = '';

-- Now make it NOT NULL
ALTER TABLE services 
ALTER COLUMN model_version SET NOT NULL;

-- Step 9: Create index on services for efficient lookups by model version
CREATE INDEX IF NOT EXISTS idx_service_model_version ON services (model_id, model_version);

-- Step 10: Set version_updated_at for existing services
UPDATE services 
SET version_updated_at = published_on 
WHERE version_updated_at IS NULL;

COMMIT;

-- Verification queries (run these to verify migration)
-- SELECT model_id, version, version_status, is_immutable FROM models LIMIT 5;
-- SELECT service_id, model_id, model_version, version_updated_at FROM services LIMIT 5;
-- SELECT COUNT(*) FROM models WHERE version_status = 'active';
-- SELECT COUNT(*) FROM models WHERE version_status = 'deprecated';

