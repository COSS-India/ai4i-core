#!/bin/bash
# Create ai4i-core application databases (auth + core).
# Names come from AUTH_DB_NAME / MODEL_MANAGEMENT_DB_NAME (see docker-compose/.env).
# ai4i_platform_db is already created via POSTGRES_DB.
set -euo pipefail

AUTH_DB_NAME="${AUTH_DB_NAME:-ai4iplatform_auth}"
MODEL_MANAGEMENT_DB_NAME="${MODEL_MANAGEMENT_DB_NAME:-ai4iplatform_core}"

create_db_if_missing() {
  local db="$1"
  local exists
  exists="$(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '${db}'")"
  if [ "${exists}" = "1" ]; then
    echo "Database ${db} already exists"
  else
    echo "Creating database ${db}"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
      -c "CREATE DATABASE ${db}"
  fi
}

create_db_if_missing "${AUTH_DB_NAME}"
create_db_if_missing "${MODEL_MANAGEMENT_DB_NAME}"
