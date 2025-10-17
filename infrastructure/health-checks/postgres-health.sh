#!/bin/bash

# PostgreSQL health check script
# This script checks if PostgreSQL is healthy and all required databases exist

set -e

echo "Checking PostgreSQL health..."

# Check if PostgreSQL is accepting connections
if ! pg_isready -h localhost -p 5432 -U "${POSTGRES_USER:-dhruva_user}"; then
    echo "PostgreSQL is not accepting connections"
    exit 1
fi

# Execute a simple query to verify database is operational
if ! psql -h localhost -p 5432 -U "${POSTGRES_USER:-dhruva_user}" -d "${POSTGRES_DB:-dhruva_platform}" -c "SELECT 1;" > /dev/null 2>&1; then
    echo "PostgreSQL database is not operational"
    exit 1
fi

# Check that all required databases exist
REQUIRED_DATABASES=("auth_db" "config_db" "metrics_db" "telemetry_db" "alerting_db" "dashboard_db")

for db in "${REQUIRED_DATABASES[@]}"; do
    if ! psql -h localhost -p 5432 -U "${POSTGRES_USER:-dhruva_user}" -d "$db" -c "SELECT 1;" > /dev/null 2>&1; then
        echo "Required database $db does not exist or is not accessible"
        exit 1
    fi
done

echo "PostgreSQL is healthy and all required databases exist"
exit 0
