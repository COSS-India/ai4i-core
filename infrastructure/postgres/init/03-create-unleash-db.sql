-- Create the Unleash database if it doesn't exist
-- Note: PostgreSQL doesn't support CREATE DATABASE IF NOT EXISTS
-- This script should be run manually or via init script

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'unleash') THEN
        CREATE DATABASE unleash
            WITH ENCODING = 'UTF8'
            LC_COLLATE = 'en_US.utf8'
            LC_CTYPE = 'en_US.utf8'
            TABLESPACE = pg_default
            CONNECTION LIMIT = -1;
    END IF;
END
$$;

