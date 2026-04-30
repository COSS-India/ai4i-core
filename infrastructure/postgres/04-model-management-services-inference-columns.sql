-- Model management DB: align legacy `services` table with ORM (inference_server_type / ssl_verify).
-- Idempotent. Apply to database model_management_db, e.g.:
--   psql -U ... -d model_management_db -f 04-model-management-services-inference-columns.sql

ALTER TABLE services
  ADD COLUMN IF NOT EXISTS inference_server_type VARCHAR(32) NOT NULL DEFAULT 'triton';

ALTER TABLE services
  ADD COLUMN IF NOT EXISTS ssl_verify BOOLEAN NOT NULL DEFAULT true;
