<<<<<<< HEAD
=======
-- Initialize all required databases for microservices
-- This script is automatically executed when PostgreSQL container starts for the first time

-- Create databases for each microservice using DO blocks for better compatibility
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'auth_db') THEN
        CREATE DATABASE auth_db;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'config_db') THEN
        CREATE DATABASE config_db;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metrics_db') THEN
        CREATE DATABASE metrics_db;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'telemetry_db') THEN
        CREATE DATABASE telemetry_db;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'alerting_db') THEN
        CREATE DATABASE alerting_db;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dashboard_db') THEN
        CREATE DATABASE dashboard_db;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'model_management_db') THEN
        CREATE DATABASE model_management_db;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'unleash') THEN
        CREATE DATABASE unleash;
    END IF;
END
$$;

SELECT 'CREATE DATABASE konga'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'konga')\gexec

-- Grant all privileges on each database to the configured PostgreSQL user
GRANT ALL PRIVILEGES ON DATABASE auth_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE config_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE metrics_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE telemetry_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE alerting_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE dashboard_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE model_management_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE konga TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE unleash TO dhruva_user;

-- Add comments documenting which service uses each database
COMMENT ON DATABASE auth_db IS 'Authentication & Authorization Service database';
COMMENT ON DATABASE config_db IS 'Configuration Management Service database';
COMMENT ON DATABASE metrics_db IS 'Metrics Collection Service database';
COMMENT ON DATABASE telemetry_db IS 'Telemetry Service database';
COMMENT ON DATABASE alerting_db IS 'Alerting Service database';
COMMENT ON DATABASE dashboard_db IS 'Dashboard Service database';
COMMENT ON DATABASE model_management_db IS 'Model Management Service database';
COMMENT ON DATABASE konga IS 'Kong Manager (Konga) database';
COMMENT ON DATABASE unleash IS 'Unleash feature flag management database';
>>>>>>> 65b91282ea6b20c576db0d431b16ce8905cf3f57
