-- Service ID Hash Migration Rollback
-- Reverts unique constraint changes from (model_id, model_version, name) 

\c model_management_db;

-- 1. Drop new unique constraint
ALTER TABLE services DROP CONSTRAINT IF EXISTS uq_model_id_version_service_name;

-- 2. Drop indexes
DROP INDEX IF EXISTS idx_services_model_id_version;
DROP INDEX IF EXISTS idx_services_name;

-- Note: This rollback does NOT revert the service_id values to user-entered strings.
-- That would require manual data restoration from a backup.
-- The service_id column will retain its hash values, but the unique constraint
-- on (model_id, model_version, name) will be removed.

SELECT 'Rollback completed' as status;
