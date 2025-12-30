#!/bin/bash
# Configure PostgreSQL authentication for Konga compatibility
# This script runs after PostgreSQL is initialized

# Update password encryption to md5 for compatibility with older clients
echo "host all all 0.0.0.0/0 md5" >> /var/lib/postgresql/data/pg_hba.conf
echo "host all all ::/0 md5" >> /var/lib/postgresql/data/pg_hba.conf

# Reload PostgreSQL configuration
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT pg_reload_conf();" || true

echo "PostgreSQL authentication configured for Konga compatibility"


