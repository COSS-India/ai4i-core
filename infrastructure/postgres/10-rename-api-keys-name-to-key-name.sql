-- Migration: Rename api_keys.name to api_keys.key_name
-- This aligns the database schema with the SQLAlchemy model

\c auth_db;

-- Rename the column from 'name' to 'key_name'
ALTER TABLE api_keys RENAME COLUMN name TO key_name;

-- Add comment to document the change
COMMENT ON COLUMN api_keys.key_name IS 'Name/label for the API key';

