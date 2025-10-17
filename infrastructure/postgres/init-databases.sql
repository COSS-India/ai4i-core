-- Initialize all required databases for microservices
-- This script is automatically executed when PostgreSQL container starts for the first time

-- Create databases for each microservice
SELECT 'CREATE DATABASE auth_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'auth_db')\gexec

SELECT 'CREATE DATABASE config_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'config_db')\gexec

SELECT 'CREATE DATABASE metrics_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metrics_db')\gexec

SELECT 'CREATE DATABASE telemetry_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'telemetry_db')\gexec

SELECT 'CREATE DATABASE alerting_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'alerting_db')\gexec

SELECT 'CREATE DATABASE dashboard_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dashboard_db')\gexec

-- Grant all privileges on each database to the configured PostgreSQL user
GRANT ALL PRIVILEGES ON DATABASE auth_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE config_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE metrics_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE telemetry_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE alerting_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE dashboard_db TO dhruva_user;

-- Add comments documenting which service uses each database
COMMENT ON DATABASE auth_db IS 'Authentication & Authorization Service database';
COMMENT ON DATABASE config_db IS 'Configuration Management Service database';
COMMENT ON DATABASE metrics_db IS 'Metrics Collection Service database';
COMMENT ON DATABASE telemetry_db IS 'Telemetry Service database';
COMMENT ON DATABASE alerting_db IS 'Alerting Service database';
COMMENT ON DATABASE dashboard_db IS 'Dashboard Service database';
