# Setup Guide

This guide provides step-by-step instructions for setting up and running the AI4I Core platform.

## Prerequisites

- **[Docker](https://docs.docker.com/get-started/get-docker/)** and **[Docker Compose](https://docs.docker.com/compose/install/)** installed
- **[Git](https://git-scm.com/install/)** installed
- **[Python](https://www.python.org/downloads/)** and **[pip](https://pip.pypa.io/en/stable/installation/)** installed
- At least **8GB RAM** and **20GB disk space**

## Important Note

**This guide uses `docker-compose-local.yml` for local development and testing.** All Docker Compose commands will use the `-f docker-compose-local.yml` flag to specify this configuration file.

## Step 1: Clone the Repository

```bash
git clone git@github.com:COSS-India/ai4i-core.git
cd ai4i-core
```

## Step 2: Configure Environment Variables

### 2.1 Create the Root Environment File

```bash
cp env.template .env
```

Open `.env` and fill in the **Database Configuration** section (around **line 107**). Replace the `<YOUR_...>` placeholders with your values. Example:

```bash
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ai4i_platform

# Databases the migration framework actually creates (one per Alembic
# versions/<dir>, see infrastructure/databases/migrations/postgres/alembic/versions/):
AUTH_DB_NAME=ai4iplatform_auth
MODEL_MANAGEMENT_DB_NAME=ai4iplatform_core
POLICY_DB_NAME=policy_db
ALERTING_DB_NAME=alerting_db
```

> Note: `env.template` also contains `DASHBOARD_DB_NAME` and `METRICS_DB_NAME`. These have no Alembic migration directory and are not created by `migrate.sh` — leaving them at defaults is fine; they are read by services that no longer exist.

### 2.2 Generate All Service Environment Files

Run the setup script to generate `.env` files for every service, the frontend, and Alembic migrations. The script reads your root `.env` and substitutes the values into each service's `env.template`:

```bash
./scripts/setup-env.sh
```

This command will copy `env.template` to `.env` for each service. It always overwrites existing `.env` files, so you can re-run it any time you change values in the root `.env`.

## Step 3: Build Docker Images

Build all the Docker images using the local development compose file:

```bash
docker compose -f docker-compose-local.yml build
```

**Note:** The first build may take 20-40 minutes depending on your machine and network speed. Subsequent builds will be faster due to Docker's layer caching.

## Step 4: Start Infrastructure Services

Start the infrastructure services (PostgreSQL, Redis, Kafka, etc.). Application services depend on databases being initialized:

```bash
docker compose -f docker-compose-local.yml up -d postgres redis kafka zookeeper
```

Wait for all infrastructure services to be healthy:

```bash
docker compose -f docker-compose-local.yml ps
```

You should see `postgres`, `redis`, `kafka`, and `zookeeper` all showing as "healthy" or "Up".

If any service is not running, start the specific service using:
```bash
docker compose -f docker-compose-local.yml up -d <service-name>
```

## Step 5: Initialize Databases

The platform uses Alembic for database migrations, with a thin CLI wrapper (`infrastructure/databases/cli.py`) for convenience. For full details see [`infrastructure/databases/MIGRATIONS.md`](../infrastructure/databases/MIGRATIONS.md).

### Step 5.1: Install Migration Framework Dependencies

**Linux/macOS:**
```bash
cd infrastructure/databases
pip3 install -r requirements.txt
cd ../..
```

**Windows:**
```bash
cd infrastructure/databases
pip install -r requirements.txt
cd ..\..
```

### Step 5.2: Run All Migrations

Run migrations for all databases at once.

```bash
./scripts/migrate.sh all upgrade
```

This command will:
- Create all required databases (`ai4iplatform_auth`, `ai4iplatform_core`, `alerting_db`, `policy_db`, `ai4i_platform_db`)
- Create all tables, indexes, constraints, and triggers
- Seed the default data — the seed steps are themselves Alembic migrations (`*_seed_*.py` under `infrastructure/databases/migrations/postgres/alembic/versions/`), so they run as part of the same `upgrade`. This includes:
  - Default admin user: `admin@ai4inclusion.org` / `ADMIN_PASSWORD` (the password is the literal string `ADMIN_PASSWORD` unless you override it by setting `ADMIN_DEFAULT_PASSWORD` in the environment before running the migration)
  - Default roles: `ADMIN`, `USER`, `GUEST`, `MODERATOR`, `TENANT ADMIN`, with permissions wired up per role
  - Service configurations and default alert rules

**Note:** The migration framework automatically handles database creation, so you don't need to create databases manually. There is no separate `seed` step — re-running `./scripts/migrate.sh all upgrade` is the way to (re-)apply seed data.

## Step 6: Start Application Services

Now that the databases are ready, start the remaining containerised services (auth, platform-core, frontend) and the monitoring stack:

```bash
docker compose -f docker-compose-local.yml up -d
```

**Note:** Docker Compose will automatically start services in the correct order based on their dependencies.

### Run `inference-service` natively (uvicorn)

`inference-service` is **not** managed by Docker Compose — it runs directly on the host so iteration is fast and the local Python debugger can attach. After the infrastructure containers are up:

```bash
cd services/inference-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py    # listens on http://localhost:8090
```

Or use VS Code's "Debug Inference Service" launch configuration in `.vscode/launch.json`.

Prometheus and Alertmanager inside the compose network resolve `inference-service` to `host-gateway` so they can scrape and webhook to the host-side process.

### Verify Services Are Running

Check the status of all services:

```bash
docker compose -f docker-compose-local.yml ps
```

All services should show as "Up" or "healthy". Services may take 30-60 seconds to become healthy after starting. If any containers stay in **Created** state or you see other errors, see [Troubleshooting](#troubleshooting) for help.

### View Logs (Optional)

To view logs for all services:

```bash
docker compose -f docker-compose-local.yml logs -f
```

To view logs for a specific service:

```bash
docker compose -f docker-compose-local.yml logs -f <service-name>
# Example: docker compose -f docker-compose-local.yml logs -f auth-service
```

## Step 7: Access the Platform

Once all services are running, use the table below to find URLs and ports. The **Compose service** column gives the service name to use with Docker Compose (for example, `docker compose -f docker-compose-local.yml logs -f auth-service`).

| Service / Tool | Compose service | URL | Port |
|----------------|-----------------|-----|------|
| Frontend | simple-ui-frontend | http://localhost:3000 | 3000 |
| Auth Service | auth-service | http://localhost:8081/docs | 8081 |
| Platform Core Service | platform-core-service | http://localhost:8102/docs | 8102 |
| Inference Service | *(runs natively, see Step 6)* | http://localhost:8090/docs | 8090 |
| Prometheus | prometheus | http://localhost:9090 | 9090 |
| Alertmanager | alertmanager | http://localhost:9095 | 9095 |
| Grafana | grafana | http://localhost:3001 | 3001 |
| Jaeger | jaeger | http://localhost:16686 | 16686 |
| OpenSearch Dashboards | opensearch-dashboards | http://localhost:5602 | 5602 |

### Default Credentials

**Platform Admin:**
- **Username**: `admin`
- **Email**: `admin@ai4inclusion.org`
- **Password**: the literal string `ADMIN_PASSWORD` (override by setting `ADMIN_DEFAULT_PASSWORD` in the environment before running the migration)
- **Role**: ADMIN (all permissions)

## Troubleshooting

### Services not starting

1. Check logs: `docker compose -f docker-compose-local.yml logs <service-name>`
2. Verify environment files exist in each service directory
3. Check if ports are already in use: `netstat -tulpn | grep <port>` (Windows: `netstat -ano | findstr <port>`)

### Containers in Created State

If some containers stay in a **Created** state and do not start, bring them up explicitly:

```bash
docker compose -f docker-compose-local.yml up -d <service-name>
```

Replace `<service-name>` with the service that is stuck (e.g. `auth-service`, `platform-core-service`).

### Database connection errors

1. Ensure PostgreSQL is running: `docker compose -f docker-compose-local.yml ps postgres`
2. Check PostgreSQL is healthy: `docker compose -f docker-compose-local.yml ps | grep postgres`
3. Re-run migrations if needed (seed data is baked into the migrations):

   ```bash
   ./scripts/migrate.sh all upgrade
   ```

### Postgres volume or "no such file or directory" for pg_data

The default `docker-compose-local.yml` uses a Docker-managed volume (no bind mount), so this error should not occur. If you see it, your compose file (or an override) likely uses a bind mount. Create the host directory that matches `volumes.postgres-data.driver_opts.device` in that file before starting Postgres, for example:

```bash
mkdir -p /home/ubuntu/ai4i-v/volumes/pg_data
```

Or use a path in the project: `mkdir -p volumes/pg_data` and set `device: "./volumes/pg_data"` under `postgres-data.driver_opts`.

### Default admin login not working

Use the credentials from the [Default Credentials](#default-credentials) section: **Username** `admin`, **Email** `admin@ai4inclusion.org`, **Password** `ADMIN_PASSWORD`.

If login still fails:

1. Check if the auth service is healthy:
   ```bash
   docker compose -f docker-compose-local.yml ps auth-service
   ```

2. Re-run migrations to recreate the admin user (seed data is part of the migrations):

   ```bash
   ./scripts/migrate.sh all upgrade
   ```

3. Check auth service logs:
   ```bash
   docker compose -f docker-compose-local.yml logs auth-service
   ```

### Port conflicts

If ports are already in use, you can modify the port mappings in `docker-compose-local.yml` or stop the conflicting services.

## Architecture Notes

### Local Development Setup

This `docker-compose-local.yml` configuration is optimized for local development:

- **Health checks**: Every containerised service has a `healthcheck` on a 10-second interval — `docker compose ps` will tell you whether a service is `healthy`, `starting`, or `unhealthy`
- **Monitoring stack**: Full observability with Prometheus, Alertmanager, Grafana, Jaeger, and OpenSearch
- **Hybrid run model**: Long-lived services (`auth-service`, `platform-core-service`, `simple-ui-frontend`) run in Docker. `inference-service` is intentionally **not** in compose — it runs natively on the host so iteration is fast and a Python debugger can attach (see Step 6)

### Production Deployment

For production deployment with load balancing and enhanced security features, refer to the production docker-compose configuration.

## Next Steps

- Explore the per-service Swagger UIs:
  - Auth — http://localhost:8081/docs
  - Platform Core — http://localhost:8102/docs
  - Inference — http://localhost:8090/docs
- Test the frontend at http://localhost:3000
- Review service logs and metrics in Grafana (http://localhost:3001)

## Stopping Services

To stop all services:

```bash
docker compose -f docker-compose-local.yml down
```

To stop and remove all data (volumes):

```bash
docker compose -f docker-compose-local.yml down -v
```

On some Linux systems you may need `sudo`:

```bash
sudo docker compose -f docker-compose-local.yml down -v
```

## Fresh Start: Starting from Scratch

To reset the installation and start over:

Stop containers and remove volumes for this project.

```bash
docker compose -f docker-compose-local.yml down -v
```

On Linux, if you run Docker with sudo:

```bash
sudo docker compose -f docker-compose-local.yml down -v
```
Then run the setup again from [Step 1: Clone the Repository](#step-1-clone-the-repository) (or from [Step 3](#step-3-build-docker-images) if you keep the repo and only need to rebuild).

## Optional Configurations

After the platform is running, you can enable or customize these optional features:

**Need Help?** Open an issue on GitHub.
