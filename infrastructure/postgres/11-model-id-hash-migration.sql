-- Model ID Hash Migration
-- Changes unique constraint from (model_id, version) to (name, version)
-- Run AFTER the Python data migration script (migrate_model_id_to_hash.py)

\c model_management_db;

-- 1. Drop foreign key constraint (depends on unique constraint)
ALTER TABLE services DROP CONSTRAINT IF EXISTS services_model_id_fkey CASCADE;

-- 2. Drop old unique constraint
ALTER TABLE models DROP CONSTRAINT IF EXISTS uq_model_id_version;
ALTER TABLE models DROP CONSTRAINT IF EXISTS models_model_id_key;

-- 3. Ensure name is NOT NULL
UPDATE models SET name = model_id WHERE name IS NULL OR name = '';
ALTER TABLE models ALTER COLUMN name SET NOT NULL;

-- 4. Fix duplicates by appending model_id suffix to make (name, version) unique
WITH duplicates AS (
    SELECT id, name, version, model_id,
           ROW_NUMBER() OVER (PARTITION BY name, version ORDER BY created_at, id) as rn
    FROM models
)
UPDATE models m
SET name = d.name || '_' || SUBSTRING(d.model_id, 1, 8)
FROM duplicates d
WHERE m.id = d.id AND d.rn > 1;

-- 5. Add new unique constraint on (name, version)
ALTER TABLE models ADD CONSTRAINT uq_name_version UNIQUE (name, version);

-- 6. Create index for model_name filter
CREATE INDEX IF NOT EXISTS idx_models_name ON models(name);

SELECT 'Migration completed' as status;
