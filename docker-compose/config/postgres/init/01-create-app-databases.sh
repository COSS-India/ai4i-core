#!/bin/bash
# Create ai4i-core application databases (auth + core).
# ai4i_platform_db is already created via POSTGRES_DB.
set -euo pipefail

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

create_db_if_missing ai4iplatform_auth
create_db_if_missing ai4iplatform_core
