#!/bin/bash
# Script to run the fix-audit-trigger SQL file via Docker

set -e

echo "Running fix-audit-trigger SQL file via Docker..."

# Get the database connection details from docker-compose or environment
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5434}"
DB_USER="${POSTGRES_USER:-dhruva_user}"
DB_PASSWORD="${POSTGRES_PASSWORD:-dhruva_secure_password_2024}"
DB_NAME="alerting_db"

# Check if running inside Docker or on host
if [ -f /.dockerenv ]; then
    # Running inside Docker container
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p 5432 -U "$DB_USER" -d "$DB_NAME" -f /docker-entrypoint-initdb.d/12-fix-audit-trigger-function.sql
else
    # Running on host, use docker exec
    CONTAINER_NAME="ai4v-postgres"
    
    # Check if container is running
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        echo "Error: PostgreSQL container '$CONTAINER_NAME' is not running"
        echo "Please start it with: docker-compose up -d postgres"
        exit 1
    fi
    
    # Copy SQL file to container and execute
    docker cp 12-fix-audit-trigger-function.sql "$CONTAINER_NAME:/tmp/fix-trigger.sql"
    docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -f /tmp/fix-trigger.sql
    docker exec "$CONTAINER_NAME" rm /tmp/fix-trigger.sql
    
    echo "✅ Successfully applied fix-audit-trigger SQL file"
fi
