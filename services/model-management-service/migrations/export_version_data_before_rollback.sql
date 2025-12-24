-- Export script to backup version data before rollback
-- Run this BEFORE running rollback_model_versioning.sql
-- This will create backup tables with all version information

BEGIN;

-- ============================================================================
-- STEP 1: Create backup tables
-- ============================================================================

-- Backup all model versions
CREATE TABLE IF NOT EXISTS models_version_backup AS
SELECT 
    id,
    model_id,
    version,
    version_status,
    release_notes,
    is_immutable,
    name,
    description,
    submitted_on,
    updated_on,
    is_published,
    published_at,
    unpublished_at,
    created_at,
    updated_at,
    CURRENT_TIMESTAMP AS backup_timestamp
FROM models;

-- Backup service version mappings
CREATE TABLE IF NOT EXISTS services_version_backup AS
SELECT 
    id,
    service_id,
    model_id,
    model_version,
    version_updated_at,
    name,
    endpoint,
    CURRENT_TIMESTAMP AS backup_timestamp
FROM services;

-- ============================================================================
-- STEP 2: Create a mapping table showing which version to keep per model
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_version_keep_mapping AS
SELECT DISTINCT ON (model_id) 
    model_id,
    id AS model_id_to_keep,
    version AS version_to_keep,
    version_status,
    name
FROM models
ORDER BY model_id, 
    CASE WHEN version_status = 'active' THEN 1 ELSE 2 END,
    version DESC;

-- ============================================================================
-- STEP 3: Export to CSV files (optional, uncomment if needed)
-- ============================================================================

-- Uncomment these lines to export to CSV files
-- Note: Requires COPY privileges and file system access

-- COPY (SELECT * FROM models_version_backup) 
-- TO '/tmp/models_version_backup.csv' WITH CSV HEADER;

-- COPY (SELECT * FROM services_version_backup) 
-- TO '/tmp/services_version_backup.csv' WITH CSV HEADER;

-- COPY (SELECT * FROM model_version_keep_mapping) 
-- TO '/tmp/model_version_keep_mapping.csv' WITH CSV HEADER;

COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check backup tables were created
SELECT 
    'models_version_backup' AS table_name, 
    COUNT(*) AS row_count 
FROM models_version_backup
UNION ALL
SELECT 
    'services_version_backup' AS table_name, 
    COUNT(*) AS row_count 
FROM services_version_backup
UNION ALL
SELECT 
    'model_version_keep_mapping' AS table_name, 
    COUNT(*) AS row_count 
FROM model_version_keep_mapping;

-- Show which versions will be kept vs deleted
SELECT 
    m.model_id,
    m.version,
    m.version_status,
    CASE 
        WHEN m.id = k.model_id_to_keep THEN 'KEEP'
        ELSE 'DELETE'
    END AS action
FROM models m
LEFT JOIN model_version_keep_mapping k ON m.model_id = k.model_id
ORDER BY m.model_id, m.version;

-- Show service version mappings that will be lost
SELECT 
    s.service_id,
    s.name AS service_name,
    s.model_id,
    s.model_version,
    m.version_status,
    CASE 
        WHEN s.model_version = k.version_to_keep THEN 'OK - version will be kept'
        ELSE 'WARNING - version will be deleted'
    END AS status
FROM services s
LEFT JOIN models m ON s.model_id = m.model_id AND s.model_version = m.version
LEFT JOIN model_version_keep_mapping k ON s.model_id = k.model_id
ORDER BY s.service_id;

-- ============================================================================
-- RESTORATION QUERIES (for reference, if needed after rollback)
-- ============================================================================

-- To restore a specific model version after rollback:
-- INSERT INTO models (
--     id, model_id, version, name, description, ...
-- )
-- SELECT 
--     id, model_id, version, name, description, ...
-- FROM models_version_backup
-- WHERE model_id = 'your-model-id' AND version = 'your-version';

-- To restore service version mappings:
-- UPDATE services s
-- SET model_version = (
--     SELECT model_version 
--     FROM services_version_backup svb 
--     WHERE svb.service_id = s.service_id
-- )
-- WHERE EXISTS (
--     SELECT 1 FROM services_version_backup svb 
--     WHERE svb.service_id = s.service_id
-- );

