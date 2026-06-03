# Setup Guide

This guide provides step-by-step instructions for setting up and running the AI4I Core platform locally.

**Run model**: infrastructure (PostgreSQL, Redis, Kafka, observability stack) runs in Docker; the three application services (`auth-service`, `platform-core-service`, `inference-service`) run natively on the host via `uvicorn` / `python main.py` so you can iterate quickly and attach a debugger.

## Prerequisites

- **[Docker](https://docs.docker.com/get-started/get-docker/)** and **[Docker Compose](https://docs.docker.com/compose/install/)** installed
- **[Python 3.11](https://www.python.org/downloads/)** and **[pip](https://pip.pypa.io/en/stable/installation/)** installed
- **[Git](https://git-scm.com/install/)** installed
- At least **8GB RAM** and **20GB disk space**

## Step 1: Clone the Repository

```bash
git clone git@github.com:COSS-India/ai4i-core.git
cd ai4i-core
```

## Step 2: Create the Root Environment File

Docker Compose reads a root `.env` for variables it substitutes into the infrastructure service definitions (Postgres credentials, Redis password, Kafka listeners). Create it from the template and fill in the required values:

```bash
cp env.template .env
```

Open `.env` and set the required values:

```bash
# PostgreSQL — credentials for the Postgres container
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=ai4i_platform_db

# Redis
REDIS_PASSWORD=changeme

# Kafka — host-accessible address (9093 is the host-mapped port for 9092 inside Docker)
KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9093,PLAINTEXT_INTERNAL://kafka:29092
```

> **Migration variables are separate.** The root `.env` is only for Docker Compose infrastructure. Database names, Alembic host/port, and per-DB credentials go in `infrastructure/databases/migrations/postgres/alembic/.env` — configured in Step 4 below.

## Step 3: Start Infrastructure Services

### Option A: Minimal (required services only)

Only `postgres` and `redis` are strictly required for the three application services to start:

```bash
docker compose -f docker-compose-local.yml up -d postgres redis
```

### Option B: Full observability stack (recommended)

Adds Kafka (trace transport), OpenSearch (trace/log storage), Prometheus, Grafana, and Alertmanager:

```bash
docker compose -f docker-compose-local.yml up -d \
  postgres redis \
  zookeeper kafka \
  opensearch opensearch-init \
  prometheus alertmanager grafana node-exporter \
  fluent-bit opensearch-dashboards
```


Wait for the core services to become healthy:

```bash
docker compose -f docker-compose-local.yml ps
```

`postgres` and `redis` must show **healthy** before you proceed. If running the full stack, wait for `kafka` and `opensearch` too.

If any service is not running, start it explicitly:

```bash
docker compose -f docker-compose-local.yml up -d <service-name>
```

## Step 4: Initialize Databases

The platform uses Alembic for database migrations. Run them from the host using the CLI wrapper (`infrastructure/databases/cli.py`). For full details see [`infrastructure/databases/MIGRATIONS.md`](../infrastructure/databases/MIGRATIONS.md).

### Step 4.1: Create the Alembic Environment File

Copy the template and fill in your values:

```bash
cp infrastructure/databases/migrations/postgres/alembic/env.template \
   infrastructure/databases/migrations/postgres/alembic/.env
```

Open that file and replace every placeholder. Key values when running migrations from the host (Postgres is in Docker, mapped to `localhost:5432`):

```bash
AUTH_DB_USER=postgres
AUTH_DB_PASSWORD=postgres
AUTH_DB_HOST=localhost
AUTH_DB_PORT=5432
AUTH_DB_NAME=ai4iplatform_auth
AUTH_SERVICE_DB_NAME=ai4iplatform_auth

APP_DB_USER=postgres
APP_DB_PASSWORD=postgres
APP_DB_HOST=localhost
APP_DB_PORT=5432
APP_DB_NAME=ai4iplatform_core

CORE_SERVICE_DB_NAME=ai4iplatform_core

POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

CONFIG_DB_NAME=config_db
TELEMETRY_DB_NAME=telemetry_db
AI4I_PLATFORM_DB_NAME=ai4i_platform_db
```

### Step 4.2: Install Migration Framework Dependencies

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

### Step 4.3: Run All Migrations

```bash
./scripts/migrate.sh all upgrade
```

This command will:
- Create all required databases (`ai4iplatform_auth`, `ai4iplatform_core`, `config_db`, `telemetry_db`, `ai4i_platform_db`)
- Apply all table, index, constraint, and trigger migrations
- Seed default data (admin user, roles, permissions, alert rules) — seed steps are Alembic migrations so they run automatically. This includes:
  - Default admin user: `admin@ai4inclusion.org` / `ADMIN_PASSWORD` (override by setting `ADMIN_DEFAULT_PASSWORD` in the environment before running the migration)
  - Default roles: `ADMIN`, `USER`, `GUEST`, `MODERATOR`, `TENANT ADMIN`, with permissions wired up per role
  - Service configurations and default alert rules

**Note:** Re-running `./scripts/migrate.sh all upgrade` is the way to re-apply seed data. There is no separate seed step.

## Step 5: Auth Service

The auth service handles authentication, authorization, RBAC, API keys, and JWT issuance. See [`services/auth-service/README.md`](../services/auth-service/README.md) and [`docs/architecture/01-auth-service.md`](architecture/01-auth-service.md) for full details.

### Step 5.1: Configure

```bash
cp services/auth-service/env.template services/auth-service/.env
```

Open `services/auth-service/.env` and set:

```bash
# PostgreSQL — point to the Docker-hosted Postgres
AUTH_DB_USER=postgres
AUTH_DB_PASSWORD=postgres
AUTH_DB_HOST=localhost
AUTH_DB_PORT=5432

# Redis — point to the Docker-hosted Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=changeme   # must match REDIS_PASSWORD in root .env
```

### Step 5.2: Install Dependencies and Run

```bash
cd services/auth-service
pip install -r requirements.txt
```

**Using uvicorn directly:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

**Using the module entrypoint:**
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

The service is ready when you see `Application startup complete` in the logs. Verify at **http://localhost:8081/docs**.


```bash
cd ../..
```

## Step 6: Platform Core Service

The platform core service is the model and service registry, alert management, and telemetry query API. See [`services/platform-core-service/README.md`](../services/platform-core-service/README.md) and [`docs/architecture/02-platform-core-service.md`](architecture/02-platform-core-service.md) for full details.

### Step 6.1: Configure

```bash
cp services/platform-core-service/env.template services/platform-core-service/.env
```

Open `services/platform-core-service/.env` and set:

```bash
# PostgreSQL — point to the Docker-hosted Postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
CORE_DB_NAME=ai4iplatform_core

# Redis — point to the Docker-hosted Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=changeme   # must match REDIS_PASSWORD in root .env

# Auth service — already running natively on port 8081
AUTH_SERVICE_URL=http://localhost:8081

# OpenSearch — mapped to host port 9204
OPENSEARCH_URL=http://localhost:9204

# Prometheus / Alertmanager — running in Docker, mapped to host
PROMETHEUS_URL=http://localhost:9090
ALERTMANAGER_URL=http://localhost:9095

# Alert rule file paths — local repo paths (service is on the host, not in Docker)
PROMETHEUS_APPLICATION_ALERTS_PATH=infrastructure/prometheus/rules/application-alerts.yml
PROMETHEUS_INFRASTRUCTURE_ALERTS_PATH=infrastructure/prometheus/rules/infrastructure-alerts.yml
ALERTMANAGER_CONFIG_PATH=infrastructure/alertmanager/alertmanager.yml
```

### Step 6.2: Install Dependencies and Run

```bash
cd services/platform-core-service
pip install -r requirements.txt
```

**Using uvicorn directly:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8095 --reload
```

**Using the module entrypoint:**
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8095 --reload
```

The service is ready when you see `Application startup complete`. Verify at **http://localhost:8095/docs**.


```bash
cd ../..
```

## Step 7: Inference Service

The inference service is the unified multi-task inference orchestration layer. See [`services/inference-service/README.md`](../services/inference-service/README.md) and [`docs/architecture/03-inference-service.md`](architecture/03-inference-service.md) for full details.

### Step 7.1: Configure

```bash
cp services/inference-service/env.template services/inference-service/.env
```

Open `services/inference-service/.env` and set:

```bash
# Service bind address
HOST=0.0.0.0
PORT=8090

# Platform Core Service — already running natively on port 8095
MODEL_MANAGEMENT_SERVICE_URL=http://localhost:8095

# Kafka — mapped to host port 9093
KAFKA_SERVER=localhost:9093

# OpenTelemetry / Jaeger — OTLP HTTP endpoint mapped to host
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# LLM upstream (optional — only needed if using LLM task type)
LLM_DEFAULT_ENDPOINT=<YOUR_LLM_UPSTREAM_BASE_URL>
```

### Step 7.2: Install Dependencies and Run

```bash
cd services/inference-service
pip install -r requirements.txt
```

**Using the built-in entrypoint (reads HOST/PORT from `.env`):**
```bash
python main.py
```

**Using uvicorn directly:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

The service is ready when you see `Application startup complete`. Verify at **http://localhost:8090/docs**.


```bash
cd ../..
```

## Step 8: Access the Platform

Once all services are running, use the table below to find URLs and ports.

| Service / Tool | URL | Notes |
|---|---|---|
| Auth Service | http://localhost:8081/docs | Runs natively |
| Platform Core Service | http://localhost:8095/docs | Runs natively |
| Inference Service | http://localhost:8090/docs | Runs natively |
| Prometheus | http://localhost:9090 | Docker |
| Alertmanager | http://localhost:9095 | Docker |
| Grafana | http://localhost:3001 | Docker |
| OpenSearch Dashboards | http://localhost:5602 | Docker |

### Default Credentials

**Platform Admin:**
- **Username**: `admin`
- **Email**: `admin@ai4inclusion.org`
- **Password**: the literal string `ADMIN_PASSWORD` (override by setting `ADMIN_DEFAULT_PASSWORD` before running the migration)
- **Role**: ADMIN (all permissions)

## Troubleshooting

### Database connection errors from migrate.sh

Ensure Postgres is running and `POSTGRES_HOST=localhost` in `infrastructure/databases/migrations/postgres/alembic/.env`. Verify with:

```bash
docker compose -f docker-compose-local.yml ps postgres
```

Re-run migrations if needed:

```bash
./scripts/migrate.sh all upgrade
```

### Service cannot reach Postgres or Redis

When a service starts and immediately errors with a connection refused, check that `.env` inside the service directory uses `localhost` (not `postgres` or `redis` — those are Docker-internal hostnames):

```bash
grep -E "HOST|PORT" services/auth-service/.env
grep -E "HOST|PORT" services/platform-core-service/.env
```

### Service cannot reach Auth Service or Platform Core

Check the service URLs in the downstream service `.env`. Platform Core expects Auth to be at `AUTH_SERVICE_URL=http://localhost:8081`; Inference expects Platform Core at `MODEL_MANAGEMENT_SERVICE_URL=http://localhost:8095`.

### Kafka connection issues

The Kafka container is mapped to host port `9093`. If the inference service cannot connect, confirm `KAFKA_SERVER=localhost:9093` in `services/inference-service/.env`.

### Postgres volume or "no such file or directory" for pg_data

The default `docker-compose-local.yml` uses a Docker-managed volume (no bind mount), so this error should not occur. If you see it, your compose file (or an override) likely uses a bind mount. Create the host directory that matches `volumes.postgres-data.driver_opts.device` in that file before starting Postgres, for example:

```bash
mkdir -p /home/ubuntu/ai4i-v/volumes/pg_data
```

### Default admin login not working

Use the credentials from the [Default Credentials](#default-credentials) section: **Username** `admin`, **Email** `admin@ai4inclusion.org`, **Password** `ADMIN_PASSWORD`.

If login still fails:

1. Check if the auth service is healthy:
   ```bash
   curl http://localhost:8081/health
   ```

2. Re-run migrations to recreate the admin user:
   ```bash
   ./scripts/migrate.sh all upgrade
   ```

3. Check auth service logs in the terminal where it is running.

### Port conflicts

Stop the conflicting process, or change the `--port` argument when starting the affected service.

Check what is using a port:
```bash
# Linux/macOS
lsof -i :<port>
# Windows
netstat -ano | findstr <port>
```

## Architecture Notes

### Local Development Run Model

| Layer | Where it runs | How to restart |
|---|---|---|
| PostgreSQL, Redis, Kafka, Zookeeper | Docker Compose | `docker compose -f docker-compose-local.yml restart <service>` |
| Prometheus, Alertmanager, Grafana, OpenSearch, Fluent Bit | Docker Compose | same |
| `auth-service` | Native — uvicorn | restart the terminal process |
| `platform-core-service` | Native — uvicorn | restart the terminal process |
| `inference-service` | Native — python main.py / uvicorn | restart the terminal process |

### Why Services Run Natively

Running application services directly on the host means:

- **Fast iteration**: code changes reload immediately (`--reload` flag) without rebuilding a Docker image
- **Native debugger**: attach VS Code or PyCharm directly to the process
- **Simpler logs**: service output appears directly in your terminal

Infrastructure services (databases, brokers, observability) are stable dependencies that do not need frequent restarts, so Docker is a natural fit.

### Production Deployment

For production deployment with load balancing and enhanced security features, refer to the production docker-compose configuration.

## Stopping Services

Stop individual services by pressing `Ctrl+C` in the terminal running that service.

To stop all Docker infrastructure:

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

Stop containers and remove volumes:

```bash
docker compose -f docker-compose-local.yml down -v
```

Then run the setup again from [Step 3: Start Infrastructure Services](#step-3-start-infrastructure-services) (or from [Step 1](#step-1-clone-the-repository) if you want a completely clean clone).

**Need Help?** Open an issue on GitHub.
