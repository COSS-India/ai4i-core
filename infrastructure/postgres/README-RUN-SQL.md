# Running Dynamic Alert Configuration Schema

## Quick Command (Direct Docker)

Run the SQL file directly using Docker:

```bash
# Windows (PowerShell)
docker exec -i ai4v-postgres psql -U dhruva_user -d alerting_db -f /docker-entrypoint-initdb.d/11-dynamic-alert-config-schema.sql

# Or using docker compose
docker compose exec -T postgres psql -U dhruva_user -d alerting_db -f /docker-entrypoint-initdb.d/11-dynamic-alert-config-schema.sql
```

## Using the Helper Script

On Linux/Mac (or Git Bash on Windows):

```bash
./infrastructure/postgres/run-dynamic-alert-schema.sh
```

## Manual Steps

1. **Copy SQL file to container:**
   ```bash
   docker cp infrastructure/postgres/11-dynamic-alert-config-schema.sql ai4v-postgres:/tmp/11-dynamic-alert-config-schema.sql
   ```

2. **Execute SQL file:**
   ```bash
   docker exec -i ai4v-postgres psql -U dhruva_user -d alerting_db -f /tmp/11-dynamic-alert-config-schema.sql
   ```

3. **Clean up:**
   ```bash
   docker exec ai4v-postgres rm /tmp/11-dynamic-alert-config-schema.sql
   ```

## Verify Tables Were Created

```bash
docker exec -i ai4v-postgres psql -U dhruva_user -d alerting_db -c "\dt"
```

You should see tables:
- `alert_definitions`
- `alert_annotations`
- `notification_receivers`
- `routing_rules`
- `alert_config_audit_log`

## Data Persistence

**Important:** The data should persist in the Docker volume `postgres-data`. However, if you're experiencing data loss:

1. **Check if the volume exists:**
   ```bash
   docker volume ls | grep postgres-data
   ```

2. **Inspect the volume:**
   ```bash
   docker volume inspect postgres-data
   ```

3. **If data is still lost after restart**, the volume configuration in `docker-compose.yml` may need adjustment (see below).

## Automatic Execution on First Start

The SQL file will be **automatically executed** when the PostgreSQL container is first initialized (when the data directory is empty), because:
- The file is in `infrastructure/postgres/` directory
- This directory is mounted to `/docker-entrypoint-initdb.d/` in the container
- PostgreSQL automatically executes all `.sql` files in that directory on first initialization

**Note:** Files in `/docker-entrypoint-initdb.d/` only run on the **first initialization** when the database is empty. After that, you need to run SQL files manually using the commands above.
