-- Migration: Add policy column to services table
-- Description: Adds a JSONB column to store policy data (latency, cost, accuracy) for services
-- Date: 2024
-- Related Issue: Add policy management for services
--
-- IMPORTANT: Run this against model_management_db (the DB used by model-management-service).
-- Example: psql -h <host> -U <user> -d model_management_db -f 14-add-policy-column-to-services.sql
-- Or from Docker: docker compose exec postgres psql -U dhruva_user -d model_management_db -f /path/to/14-add-policy-column-to-services.sql

-- Add policy column to services table
ALTER TABLE services
ADD COLUMN IF NOT EXISTS policy JSONB;

-- Add comment to document the column
COMMENT ON COLUMN services.policy IS 'Policy data (latency, cost, accuracy) stored as JSONB. Example: {"latency": "low", "cost": "tier_3", "accuracy": "sensitive"}';

-- Create index on policy column for better query performance (GIN index for JSONB)
CREATE INDEX IF NOT EXISTS idx_services_policy ON services USING GIN (policy);
