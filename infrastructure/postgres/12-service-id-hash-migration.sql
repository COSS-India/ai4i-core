-- Service ID Hash Migration
-- Changes service_id from user-entered string to hash of (model_name, model_version, service_name)
-- Adds unique constraint on (model_id, model_version, name)
-- Run AFTER the Python data migration script (migrate_service_id_to_hash.py)

\c model_management_db;

-- 1. Fix duplicates by appending service_id suffix to make (model_id, model_version, name) unique
WITH duplicates AS (
    SELECT id, model_id, model_version, name, service_id,
           ROW_NUMBER() OVER (PARTITION BY model_id, model_version, name ORDER BY created_at, id) as rn
    FROM services
)
UPDATE services s
SET name = d.name || '_' || SUBSTRING(d.service_id, 1, 8)
FROM duplicates d
WHERE s.id = d.id AND d.rn > 1;

-- 2. Add new unique constraint on (model_id, model_version, name)
ALTER TABLE services ADD CONSTRAINT uq_model_id_version_service_name UNIQUE (model_id, model_version, name);

-- 3. Create index for service lookups by model_id and model_version
CREATE INDEX IF NOT EXISTS idx_services_model_id_version ON services(model_id, model_version);

-- 4. Create index for service_name lookup
CREATE INDEX IF NOT EXISTS idx_services_name ON services(name);

SELECT 'Migration completed' as status;
