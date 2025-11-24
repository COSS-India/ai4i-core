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
create_database_if_not_exists "unleash"

# Grant privileges
echo -e "${GREEN}Granting privileges...${NC}"
docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" <<EOF
GRANT ALL PRIVILEGES ON DATABASE auth_db TO $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE config_db TO $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE unleash TO $DB_USER;

COMMENT ON DATABASE auth_db IS 'Authentication & Authorization Service database';
COMMENT ON DATABASE config_db IS 'Configuration Management Service database';
COMMENT ON DATABASE unleash IS 'Unleash feature flag management database';
EOF

# Now run the SQL schema initialization script
echo -e "${GREEN}Running schema initialization script...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_SCRIPT="$SCRIPT_DIR/init-all-databases.sql"

# Copy the SQL script to the container
docker compose cp "$SQL_SCRIPT" postgres:/tmp/init-all-databases.sql

# Create a temporary SQL file without CREATE DATABASE statements
# since we already created the databases above
docker compose exec -T postgres sh <<'INNER_SCRIPT'
sed '/^CREATE DATABASE/,/^;/d' /tmp/init-all-databases.sql > /tmp/init-schema-only.sql
# Also remove the grant and comment statements for databases since we did those too
sed -i '/^GRANT ALL PRIVILEGES ON DATABASE/d' /tmp/init-schema-only.sql
sed -i '/^COMMENT ON DATABASE/d' /tmp/init-schema-only.sql
INNER_SCRIPT

# Execute the SQL script (schema only, databases already created)
docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -f /tmp/init-schema-only.sql || {
    echo -e "${YELLOW}Note: Some errors may be expected if tables already exist${NC}"
}

echo -e "${GREEN}Database initialization complete!${NC}"

