#!/bin/bash
# ============================================================================
# Run Model Management Audit Logs Migration
# ============================================================================
# This script runs the 13-model-management-audit-logs-migration.sql file 
# against the model_management_db database via Docker.
#
# Usage:
#   ./infrastructure/postgres/run-audit-logs-migration.sh
#   OR
#   bash infrastructure/postgres/run-audit-logs-migration.sh
# ============================================================================

set -e

# Get database connection parameters from environment or use defaults
DB_USER="${POSTGRES_USER:-dhruva_user}"
DB_PASSWORD="${POSTGRES_PASSWORD:-dhruva_secure_password_2024}"
DB_NAME="model_management_db"
CONTAINER_NAME="ai4v-postgres"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Running Model Management Audit Logs Migration...${NC}"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: PostgreSQL container '${CONTAINER_NAME}' is not running${NC}"
    echo -e "${YELLOW}Please start it with: docker compose up -d postgres${NC}"
    exit 1
fi

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="${SCRIPT_DIR}/13-model-management-audit-logs-migration.sql"

# Check if SQL file exists
if [ ! -f "$SQL_FILE" ]; then
    echo -e "${RED}Error: SQL file not found: ${SQL_FILE}${NC}"
    exit 1
fi

echo -e "${YELLOW}Executing SQL file: ${SQL_FILE}${NC}"
echo -e "${YELLOW}Target database: ${DB_NAME}${NC}"

# Copy SQL file to container
docker cp "$SQL_FILE" "${CONTAINER_NAME}:/tmp/13-model-management-audit-logs-migration.sql"

# Execute the SQL file
# Using PGPASSWORD environment variable to avoid password prompt
PGPASSWORD="${DB_PASSWORD}" docker exec -i "${CONTAINER_NAME}" \
    psql -U "${DB_USER}" -d "${DB_NAME}" \
    -f /tmp/13-model-management-audit-logs-migration.sql

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Model Management Audit Logs Migration executed successfully!${NC}"
    echo -e "${GREEN}✓ Columns added to database: ${DB_NAME}${NC}"
else
    echo -e "${RED}✗ Error executing SQL file${NC}"
    exit 1
fi

# Clean up temporary file
docker exec "${CONTAINER_NAME}" rm -f /tmp/13-model-management-audit-logs-migration.sql

echo -e "${GREEN}Done!${NC}"

