#!/usr/bin/env bash
# Create each database if missing, then upgrade it to head.
# Same order and steps as scripts/migrate.sh, without its local .env loading,
# which would point the run at localhost instead of the postgres container.
set -euo pipefail

MIGRATIONS_DIR=/repo/infrastructure/databases/migrations/postgres
cd "${MIGRATIONS_DIR}"

DATABASES=(ai4iplatform_auth ai4i_platform_db ai4iplatform_core)

for db in "${DATABASES[@]}"; do
  echo "==> ${db}: ensure database exists"
  python alembic/migration_registry.py ensure "${db}"

  # Alembic needs this database's versions directory only.
  ini="/tmp/alembic-${db}.ini"
  sed "s|^version_locations = .*|version_locations = ${MIGRATIONS_DIR}/alembic/versions/${db}|; s|%(here)s|${MIGRATIONS_DIR}|g" \
    alembic.ini > "${ini}"

  echo "==> ${db}: upgrade head"
  python -m alembic -c "${ini}" -x "db=${db}" upgrade head
done

echo "==> All migrations applied"
