-- Migration: Add permissions column to api_keys table and fix last_used column name
-- This aligns the database schema with the SQLAlchemy model

\c auth_db;

-- Add permissions column (JSON type for storing array of permission strings)
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS permissions JSONB DEFAULT '[]'::jsonb;

-- Rename last_used_at to last_used to match the model
ALTER TABLE api_keys RENAME COLUMN last_used_at TO last_used;

-- Add comment to document the change
COMMENT ON COLUMN api_keys.permissions IS 'Array of permission strings for the API key';

