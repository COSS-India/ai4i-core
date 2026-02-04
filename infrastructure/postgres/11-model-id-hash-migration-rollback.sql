-- Model ID Hash Migration Rollback
-- Reverts unique constraint from (name, version) back to (model_id, version)

\c model_management_db;

-- 1. Drop new unique constraint
ALTER TABLE models DROP CONSTRAINT IF EXISTS uq_name_version;

-- 2. Drop index
DROP INDEX IF EXISTS idx_models_name;

-- 3. Restore old unique constraint
ALTER TABLE models ADD CONSTRAINT uq_model_id_version UNIQUE (model_id, version);

-- 4. Restore foreign key (optional - only if needed)
-- ALTER TABLE services ADD CONSTRAINT services_model_id_fkey 
--     FOREIGN KEY (model_id, model_version) REFERENCES models(model_id, version);

SELECT 'Rollback completed' as status;
