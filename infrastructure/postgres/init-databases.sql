-- ============================================================================
-- Initialize All Required Databases for Microservices
-- ============================================================================
-- This script is automatically executed when PostgreSQL container starts
-- for the first time via docker-entrypoint-initdb.d
--
-- Note: For full schema initialization with tables and seed data, use:
--   ./infrastructure/postgres/init-all-databases.sh
-- ============================================================================

-- Continue execution even if some statements fail (e.g., if databases already exist)
\set ON_ERROR_STOP off

-- Create databases for each microservice
-- Note: CREATE DATABASE cannot be executed from within a DO block in PostgreSQL
-- so we use direct statements and rely on ON_ERROR_STOP off for idempotency

-- Core databases
CREATE DATABASE auth_db;
CREATE DATABASE config_db;
CREATE DATABASE model_management_db;

-- Feature flag management
CREATE DATABASE unleash
    WITH ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.utf8'
    LC_CTYPE = 'en_US.utf8'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1;

-- Grant all privileges on each database to the configured PostgreSQL user
GRANT ALL PRIVILEGES ON DATABASE auth_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE config_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE model_management_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE unleash TO dhruva_user;

-- Add comments documenting which service uses each database
COMMENT ON DATABASE auth_db IS 'Authentication & Authorization Service database';
COMMENT ON DATABASE config_db IS 'Configuration Management Service database';
COMMENT ON DATABASE model_management_db IS 'Model Management Service database - stores AI models and services registry';
COMMENT ON DATABASE unleash IS 'Unleash feature flag management database';

-- Re-enable error stopping
\set ON_ERROR_STOP on

-- ============================================================================
-- Note: This script only creates the databases.
-- For full schema setup (tables, indexes, triggers, seed data), run:
--   ./infrastructure/postgres/init-all-databases.sh
-- OR
--   docker compose exec postgres psql -U dhruva_user -d dhruva_platform \
--     -f /docker-entrypoint-initdb.d/init-all-databases.sql
-- ============================================================================
