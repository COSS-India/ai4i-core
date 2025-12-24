-- Rollback script to revert model versioning changes
-- Run this script to undo all database changes made by add_model_versioning.sql
-- WARNING: This will remove version management features and may cause data loss
-- Backup your database before running this script!

BEGIN;

-- ============================================================================
-- STEP 1: Remove indexes added for versioning
-- ============================================================================

DROP INDEX IF EXISTS idx_model_id_version;
DROP INDEX IF EXISTS idx_model_id_version_status;
DROP INDEX IF EXISTS idx_service_model_version;

-- ============================================================================
-- STEP 2: Remove composite unique constraint on models table
-- ============================================================================

ALTER TABLE models DROP CONSTRAINT IF EXISTS uq_model_id_version;

-- ============================================================================
-- STEP 3: Handle data migration for services table
-- ============================================================================

-- Before removing model_version column, we need to ensure services can still
-- reference models. Since we're reverting, we'll keep the first version of each model
-- and update services to point to that version's model_id

-- Update services to use the first (or latest) version of each model
-- This assumes we want to keep the relationship but lose version specificity
UPDATE services s
SET model_id = (
    SELECT m.model_id 
    FROM models m 
    WHERE m.model_id = s.model_id 
    ORDER BY m.version ASC 
    LIMIT 1
)
WHERE EXISTS (
    SELECT 1 FROM models m WHERE m.model_id = s.model_id
);

-- ============================================================================
-- STEP 4: Remove new columns from services table
-- ============================================================================

ALTER TABLE services 
DROP COLUMN IF EXISTS model_version,
DROP COLUMN IF EXISTS version_updated_at;

-- ============================================================================
-- STEP 5: Handle data migration for models table
-- ============================================================================

-- Before removing version columns, we need to consolidate multiple versions
-- Strategy: Keep only one version per model_id (the latest active version, or first if none active)

-- Create a temporary table to identify which models to keep
CREATE TEMP TABLE models_to_keep AS
SELECT DISTINCT ON (model_id) 
    id,
    model_id,
    version,
    submitted_on,
    updated_on,
    name,
    description,
    ref_url,
    task,
    languages,
    license,
    domain,
    inference_endpoint,
    benchmarks,
    submitter,
    is_published,
    published_at,
    unpublished_at,
    created_at,
    updated_at
FROM models
ORDER BY model_id, 
    CASE WHEN version_status = 'active' THEN 1 ELSE 2 END,
    version DESC;

-- Delete all models that are not in the keep list
DELETE FROM models
WHERE id NOT IN (SELECT id FROM models_to_keep);

-- ============================================================================
-- STEP 6: Remove new columns from models table
-- ============================================================================

ALTER TABLE models 
DROP COLUMN IF EXISTS version_status,
DROP COLUMN IF EXISTS release_notes,
DROP COLUMN IF EXISTS is_immutable;

-- ============================================================================
-- STEP 7: Restore original unique constraint on model_id
-- ============================================================================

-- Add back unique constraint on model_id (if it existed before)
-- Note: This will fail if there are duplicate model_ids, which shouldn't happen
-- after the consolidation step above
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'models_model_id_key' 
        AND conrelid = 'models'::regclass
    ) THEN
        ALTER TABLE models 
        ADD CONSTRAINT models_model_id_key UNIQUE (model_id);
    END IF;
EXCEPTION
    WHEN duplicate_table THEN
        -- Constraint already exists, do nothing
        NULL;
    WHEN unique_violation THEN
        -- There are duplicate model_ids, log warning
        RAISE WARNING 'Cannot add unique constraint: duplicate model_ids exist. Please resolve manually.';
END $$;

-- ============================================================================
-- STEP 8: Clean up temporary table
-- ============================================================================

DROP TABLE IF EXISTS models_to_keep;

-- ============================================================================
-- STEP 9: Update services to ensure they reference valid models
-- ============================================================================

-- Remove services that reference non-existent models
DELETE FROM services
WHERE model_id NOT IN (SELECT model_id FROM models);

-- ============================================================================
-- STEP 10: Verify rollback
-- ============================================================================

-- Check that version columns are removed
DO $$
DECLARE
    version_status_exists BOOLEAN;
    release_notes_exists BOOLEAN;
    is_immutable_exists BOOLEAN;
    model_version_exists BOOLEAN;
BEGIN
    -- Check models table
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'models' AND column_name = 'version_status'
    ) INTO version_status_exists;
    
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'models' AND column_name = 'release_notes'
    ) INTO release_notes_exists;
    
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'models' AND column_name = 'is_immutable'
    ) INTO is_immutable_exists;
    
    -- Check services table
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'services' AND column_name = 'model_version'
    ) INTO model_version_exists;
    
    -- Report status
    IF version_status_exists OR release_notes_exists OR is_immutable_exists THEN
        RAISE WARNING 'Some version columns still exist in models table';
    END IF;
    
    IF model_version_exists THEN
        RAISE WARNING 'model_version column still exists in services table';
    END IF;
    
    RAISE NOTICE 'Rollback verification complete. Check warnings above if any.';
END $$;

COMMIT;

-- ============================================================================
-- POST-ROLLBACK VERIFICATION QUERIES
-- ============================================================================

-- Run these queries manually to verify the rollback:

-- 1. Check models table structure
-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_name = 'models' 
-- ORDER BY ordinal_position;

-- 2. Check services table structure
-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_name = 'services' 
-- ORDER BY ordinal_position;

-- 3. Check constraints on models table
-- SELECT conname, contype 
-- FROM pg_constraint 
-- WHERE conrelid = 'models'::regclass;

-- 4. Check indexes
-- SELECT indexname, indexdef 
-- FROM pg_indexes 
-- WHERE tablename IN ('models', 'services')
-- AND indexname LIKE '%version%';

-- 5. Verify model_id uniqueness
-- SELECT model_id, COUNT(*) 
-- FROM models 
-- GROUP BY model_id 
-- HAVING COUNT(*) > 1;
-- (Should return no rows)

-- 6. Check for orphaned services
-- SELECT s.service_id, s.model_id 
-- FROM services s
-- LEFT JOIN models m ON s.model_id = m.model_id
-- WHERE m.model_id IS NULL;
-- (Should return no rows)

-- ============================================================================
-- NOTES
-- ============================================================================

-- IMPORTANT: This rollback script:
-- 1. Consolidates multiple versions of the same model into a single version
-- 2. Keeps the latest active version (or first version if none are active)
-- 3. Removes all version-specific metadata
-- 4. Restores the original unique constraint on model_id
-- 5. Updates services to reference the consolidated models

-- DATA LOSS WARNING:
-- - All version history will be lost (only one version per model kept)
-- - Release notes will be lost
-- - Version status information will be lost
-- - Service version tracking will be lost

-- RECOMMENDATION:
-- Before running this rollback:
-- 1. Export all model versions to a backup file
-- 2. Export service version mappings
-- 3. Document which versions were in use
-- 4. Create a full database backup

