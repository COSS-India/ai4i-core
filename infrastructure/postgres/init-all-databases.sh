#!/bin/bash
# ============================================================================
# Database Initialization Script Wrapper
# ============================================================================
# This script creates databases if they don't exist, then runs the SQL schema
# initialization script. This avoids the PostgreSQL limitation where CREATE
# DATABASE cannot be executed from within a function/DO block.
#
# Usage:
#   ./init-all-databases.sh
#   OR
#   docker compose exec postgres psql -U dhruva_user -d dhruva_platform -f /docker-entrypoint-initdb.d/init-all-databases.sql
# ============================================================================


# auth_db
# -----------------------
# ALTER TABLE users
# ADD COLUMN is_tenant BOOLEAN;

# ALTER TABLE user_sessions
#     ALTER COLUMN refresh_token TYPE TEXT,
#     ALTER COLUMN session_token TYPE TEXT;


# multi tenant db
# ----------------------
# ALTER TABLE tenants
# ADD COLUMN user_id INTEGER;

# CREATE INDEX idx_tenants_user_id
# ON tenants (user_id);

set -e

# Get database connection parameters from environment or use defaults
DB_USER="${POSTGRES_USER:-dhruva_user}"
DB_NAME="${POSTGRES_DB:-dhruva_platform}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Initializing databases...${NC}"

# Function to create database if it doesn't exist
create_database_if_not_exists() {
    local db_name=$1
    
    echo -e "${YELLOW}Checking for database: ${db_name}${NC}"
    
    # Check if database exists
    DB_EXISTS=$(docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT 1 FROM pg_database WHERE datname='$db_name'" 2>/dev/null || echo "")
    
    if [ "$DB_EXISTS" = "1" ]; then
        echo -e "${GREEN}Database ${db_name} already exists, skipping...${NC}"
        return 0
    else
        echo -e "${GREEN}Creating database: ${db_name}${NC}"
        docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -c "CREATE DATABASE $db_name" 2>&1
    fi
}

# Create databases
create_database_if_not_exists "auth_db"
create_database_if_not_exists "config_db"
create_database_if_not_exists "model_management_db"
create_database_if_not_exists "unleash"
create_database_if_not_exists "alerting_db"

# Grant privileges
echo -e "${GREEN}Granting privileges...${NC}"
docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" <<EOF
GRANT ALL PRIVILEGES ON DATABASE auth_db TO $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE config_db TO $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE model_management_db TO $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE unleash TO $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE alerting_db TO $DB_USER;

COMMENT ON DATABASE auth_db IS 'Authentication & Authorization Service database';
COMMENT ON DATABASE config_db IS 'Configuration Management Service database';
COMMENT ON DATABASE model_management_db IS 'Model Management Service database - stores AI models and services registry';
COMMENT ON DATABASE unleash IS 'Unleash feature flag management database';
COMMENT ON DATABASE alerting_db IS 'Alerting Service database - stores dynamic alert configurations and notification settings';
EOF

# Now run the SQL schema initialization script
echo -e "${GREEN}Running schema initialization script...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_SCRIPT="$SCRIPT_DIR/init-all-databases.sql"

# Copy the SQL script to the container
docker compose cp "$SQL_SCRIPT" postgres:/tmp/init-all-databases.sql

# Create a temporary SQL file without CREATE DATABASE, GRANT, and COMMENT statements
# since we already created the databases and granted privileges above
docker compose exec -T postgres sh <<'INNER_SCRIPT'
# Remove CREATE DATABASE statements (handles both single-line and multi-line)
# Pattern matches from line starting with CREATE DATABASE until line ending with semicolon
# This correctly handles:
#   - Single-line: CREATE DATABASE auth_db;
#   - Multi-line: CREATE DATABASE unleash ... CONNECTION LIMIT = -1;
sed '/^CREATE DATABASE/,/;$/d' /tmp/init-all-databases.sql > /tmp/init-schema-only.sql
# Remove GRANT statements for databases
sed -i '/^GRANT ALL PRIVILEGES ON DATABASE/d' /tmp/init-schema-only.sql
# Remove COMMENT statements for databases  
sed -i '/^COMMENT ON DATABASE/d' /tmp/init-schema-only.sql
INNER_SCRIPT

# Execute the SQL script (schema only, databases already created)
# The SQL file uses \set ON_ERROR_STOP off initially, then on for schema creation
# This allows it to continue past CREATE DATABASE errors (which we've removed anyway)
# We ignore exit code since some errors (like "already exists") are expected
set +e
docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -f /tmp/init-schema-only.sql
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -ne 0 ]; then
    echo -e "${YELLOW}Note: The script is idempotent and can be run multiple times safely.${NC}"
    echo -e "${YELLOW}Some errors may be expected if objects already exist, but they will be handled gracefully.${NC}"
fi

echo -e "${GREEN}Database initialization complete!${NC}"

