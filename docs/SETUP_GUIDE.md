# Setup Guide

This guide provides step-by-step instructions for setting up and running the AI4I Core platform locally.

**Run model**: infrastructure (PostgreSQL, Redis, Kafka, observability stack) runs in Docker; the three application services (`auth-service`, `platform-core-service`, `inference-service`) run natively on the host via `python3 -m uvicorn` so you can iterate quickly and attach a debugger.

## Prerequisites

- **[Docker](https://docs.docker.com/get-started/get-docker/)** and **[Docker Compose](https://docs.docker.com/compose/install/)** installed
- **[Python 3.11](https://www.python.org/downloads/)** installed (`python3 --version` should show `3.11.x`)
- **[Git](https://git-scm.com/install/)** installed
- At least **8GB RAM** and **20GB disk space**

## Step 1: Clone the Repository

```bash
git clone git@github.com:COSS-India/ai4i-core.git
cd ai4i-core
```

## Step 2: Create the Root Environment File

Create the root `.env` from the template:

```bash
cp env.template .env
```

Open `.env` and fill in the three required values — everything else has a sensible default:

```bash
# PostgreSQL — credentials for the Postgres container
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Redis
REDIS_PASSWORD=changeme
```

> **LLM task type only:** If you plan to use LLM inference, also set `LLM_UPSTREAM_BASE_URL` to the base URL of your upstream LLM server (e.g. vLLM, llama.cpp, Ollama).

## Step 3: Generate All Service Environment Files

Run the setup script to generate a `.env` for every service from its template, substituting values from the root `.env`:

```bash
./scripts/setup-env.sh
```

This creates:
- `infrastructure/databases/migrations/postgres/alembic/.env`
- `services/auth-service/.env`
- `services/platform-core-service/.env`
- `services/inference-service/.env`
- `frontend/simple-ui/.env`

Re-run this script any time you change the root `.env`.

## Step 4: Start Infrastructure Services

### Option A: Minimal (required services only)

Only `postgres`, `redis`, and `nginx-gateway` are strictly required for the three application services and the frontend to work:

```bash
docker compose -f docker-compose-local.yml up -d postgres redis nginx-gateway
```

### Option B: Full observability stack (recommended)

Adds Kafka (trace transport), OpenSearch (trace/log storage), Prometheus, Grafana, and Alertmanager:

```bash
docker compose -f docker-compose-local.yml up -d \
  postgres redis \
  zookeeper kafka \
  opensearch opensearch-init \
  prometheus alertmanager grafana node-exporter \
  fluent-bit opensearch-dashboards \
  nginx-gateway
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

## Step 5: Initialize Databases

The platform uses Alembic for database migrations. Run them from the host using the CLI wrapper (`infrastructure/databases/cli.py`). For full details see [`infrastructure/databases/MIGRATIONS.md`](../infrastructure/databases/MIGRATIONS.md).

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

```bash
./scripts/migrate.sh all upgrade
```

This command will:
- Create all required databases (`ai4iplatform_auth`, `ai4iplatform_core`, `ai4i_platform_db`)
- Apply all table, index, constraint, and trigger migrations
- Seed default data (admin user, roles, permissions, alert rules) — seed steps are Alembic migrations so they run automatically. This includes:
  - Default admin user: `admin@ai4inclusion.org` / `ADMIN_PASSWORD` (override by setting `ADMIN_DEFAULT_PASSWORD` in the environment before running the migration)
  - Default roles: `ADMIN`, `USER`, `GUEST`, `MODERATOR`, `TENANT ADMIN`, with permissions wired up per role
  - Service configurations and default alert rules

**Note:** Re-running `./scripts/migrate.sh all upgrade` is the way to re-apply seed data. There is no separate seed step.

## Step 6: Auth Service

The auth service handles authentication, authorization, RBAC, API keys, and JWT issuance. See [`services/auth-service/README.md`](../services/auth-service/README.md) and [`docs/architecture/01-auth-service.md`](architecture/01-auth-service.md) for full details.

### Step 6.1: Install Dependencies and Run

**Linux/macOS:**
```bash
cd services/auth-service
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
cd services\auth-service
python3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

The service is ready when you see `Application startup complete` in the logs. Verify at **http://localhost:8081/docs**.

```bash
deactivate
cd ../..
```

## Step 7: Platform Core Service

The platform core service is the model and service registry, alert management, and telemetry query API. See [`services/platform-core-service/README.md`](../services/platform-core-service/README.md) and [`docs/architecture/02-platform-core-service.md`](architecture/02-platform-core-service.md) for full details.

### Step 7.1: Install Dependencies and Run

**Linux/macOS:**
```bash
cd services/platform-core-service
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
cd services\platform-core-service
python3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8095 --reload
```

The service is ready when you see `Application startup complete`. Verify at **http://localhost:8095/docs**.

```bash
deactivate
cd ../..
```

## Step 8: Inference Service

The inference service is the unified multi-task inference orchestration layer. See [`services/inference-service/README.md`](../services/inference-service/README.md) and [`docs/architecture/03-inference-service.md`](architecture/03-inference-service.md) for full details.

### Step 8.1: Install Dependencies and Run

**Linux/macOS:**
```bash
cd services/inference-service
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
cd services\inference-service
python3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

The service is ready when you see `Application startup complete`. Verify at **http://localhost:8090/docs**.

```bash
deactivate
cd ../..
```

## Step 9: Frontend (Simple UI)

The Simple UI is a Next.js interface for testing ASR, TTS, and NMT services. See [`frontend/simple-ui/README.md`](../frontend/simple-ui/README.md) for full details.

### Step 9.1: Prerequisites

- **Node.js 18+** — verify with `node --version`

### Step 9.2: Set the API Key

The `setup-env.sh` script generated `frontend/simple-ui/.env` with all defaults pre-filled. The one value that cannot be auto-generated is the API key — create one via the auth service once it is running, then set it:

```bash
# frontend/simple-ui/.env
NEXT_PUBLIC_API_KEY=your_api_key_here
```

> **Note:** `nginx-gateway` must be running (`docker compose -f docker-compose-local.yml up -d nginx-gateway`) before the frontend can reach the API. It proxies all `/api/v1/…` requests to the natively-running `auth-service` (port 8081) and `platform-core-service` (port 8095).

### Step 9.3: Install Dependencies and Run

```bash
cd frontend/simple-ui
npm install
npm run dev
```

The UI is available at **http://localhost:3000**.

```bash
cd ../..
```

## Step 10: Access the Platform

Once all services are running, use the table below to find URLs and ports.

| Service / Tool | URL | Notes |
|---|---|---|
| Auth Service | http://localhost:8081/docs | Runs natively |
| Platform Core Service | http://localhost:8095/docs | Runs natively |
| Inference Service | http://localhost:8090/docs | Runs natively |
| Simple UI | http://localhost:3000 | Runs natively (Next.js) |
| **Nginx Gateway** | **http://localhost:8080** | **Docker — API gateway for the frontend** |
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
| `nginx-gateway` | Docker Compose | `docker compose -f docker-compose-local.yml restart nginx-gateway` |
| `auth-service` | Native — uvicorn | restart the terminal process |
| `platform-core-service` | Native — uvicorn | restart the terminal process |
| `inference-service` | Native — python3 main.py / uvicorn | restart the terminal process |

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

Then run the setup again from [Step 4: Start Infrastructure Services](#step-4-start-infrastructure-services) (or from [Step 1](#step-1-clone-the-repository) if you want a completely clean clone).

**Need Help?** Open an issue on GitHub.
