# Setup Guide

This guide provides step-by-step instructions for setting up and running the AI4I-Orchestrate platform locally.

**Run model**: infrastructure (PostgreSQL, Redis, Kafka, observability stack) runs in Docker; the three application services (`auth-service`, `platform-core-service`, `inference-service`) run natively on the host via `python3 -m uvicorn` so you can iterate quickly and attach a debugger.

> **Just want it running fast?** A one-command bootstrap clones the repo, installs prerequisites, and brings the stack up for you — see [SINGLE_COMMAND_SETUP.md](SINGLE_COMMAND_SETUP.md). This guide is the manual, step-by-step path (useful for understanding each piece or debugging when the automation fails).

> **Windows users:** Docker Desktop runs containers inside WSL2. You must run **all** commands in this guide — Docker, migrations, Python services, and the frontend — from a **WSL2 bash terminal**, not from PowerShell or CMD. See [Windows (WSL)](#windows-wsl) below.

## Prerequisites

- **[Docker](https://docs.docker.com/get-started/get-docker/)** and **[Docker Compose](https://docs.docker.com/compose/install/)** installed
- **[Python 3.11](https://www.python.org/downloads/)** installed (`python3 --version` should show `3.11.x`)
- **[Node.js 18+](https://nodejs.org/en/download)** installed — required for the frontend (`node --version` should show `v18.x` or higher)
- **[Git](https://git-scm.com/install/)** installed
- At least **8GB RAM** and **20GB disk space**
- **Windows only:** **[WSL2](https://learn.microsoft.com/en-us/windows/wsl/install)** with a Linux distribution (Ubuntu recommended) and **[Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)** configured to use the WSL 2 backend

## Windows (WSL)

On Windows, Docker Desktop runs containers inside WSL2. The infrastructure services (PostgreSQL, Redis) run in Docker, but the three application services and the frontend all run natively. Run **all** commands from a WSL2 terminal so Docker containers and native services share the same `localhost` network.

**Run the entire local setup inside WSL2.** All commands in this guide use bash syntax and apply unchanged on WSL.

### 1. Install and configure WSL2

```powershell
# Run once from an elevated PowerShell window on Windows
wsl --install
```

Restart if prompted, then open your Linux distro (e.g. Ubuntu) from the Start menu.

### 2. Install Docker Desktop for Windows

1. Install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/).
2. Open **Settings → General** and enable **Use the WSL 2 based engine**.
3. Open **Settings → Resources → WSL Integration** and enable integration for your Linux distro.

Verify from a WSL terminal:

```bash
docker --version
docker compose version
```

### 3. Install dev tools inside WSL

Install Python 3.11, Node.js 18+, and Git inside your WSL distro (not on Windows):

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip git curl
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
```

### 4. Clone the repo inside WSL

Clone into your WSL home directory for best file-system performance (avoid `/mnt/c/...` paths):

```bash
cd ~
git clone --branch <release-tag> git@github.com:COSS-India/ai4i-core.git
cd ai4i-core
```

Replace `<release-tag>` with the tag from the [ai4i-core releases page](https://github.com/COSS-India/ai4i-core/releases).

From this point, follow the rest of this guide in the same WSL terminal. Open additional WSL terminals for each service you need to run in parallel (auth, platform-core, inference, frontend).

## Step 1: Clone the Repository

Clone the release branch your team uses

```bash
git clone --branch <release-tag> git@github.com:COSS-India/ai4i-core.git
cd ai4i-core
```

Replace `<release-tag>` with the tag from the [ai4i-core releases page](https://github.com/COSS-India/ai4i-core/releases) (for example `release/2.2`). Use the tag that matches your project or internal documentation.

> **Note:** Omitting `--branch <release-tag>` will clone `main`, which may contain latest version.

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

### Inference service endpoints (optional, do this now to save a manual step later)

The Step 5 seed migration creates a service row for **every** model (NMT, ASR, OCR, NER, TTS, LLM, etc.) and reads each one's `endpoint` from a `TRITON_ENDPOINT_*` environment variable at migration time — if the variable is unset, the seeded `endpoint` is left **blank**, and inference calls to that service will fail until it's filled in.

If you already know the URL for one or more model servers (e.g. Triton containers), add the matching variables to this same root `.env` now, so migrations seed the correct endpoint directly. This isn't in `env.template`, so add the lines yourself — only for the servers you actually have running (or plan to have running before you need that service):

```bash
TRITON_ENDPOINT_NMT=http://localhost:8000
TRITON_ENDPOINT_ASR=http://localhost:5000
TRITON_ENDPOINT_TTS=http://localhost:9000
TRITON_ENDPOINT_OCR=http://localhost:8400
TRITON_ENDPOINT_NER=http://localhost:8300
TRITON_ENDPOINT_LANGDETECT=http://localhost:8000
TRITON_ENDPOINT_AUDIO_LANGDETECT=http://localhost:8100
TRITON_ENDPOINT_LANG_DIARIZATION=http://localhost:8600
TRITON_ENDPOINT_SPEAKER_DIARIZATION=http://localhost:8700
TRITON_ENDPOINT_TRANSLITERATION=http://localhost:8200
TRITON_ENDPOINT_LLM=http://localhost:8080
```

If you skip this (or don't know a URL yet for some services), those services will seed with a blank endpoint — set it afterward via [Step 10](#step-10-configure-inference-service-endpoints-required-if-not-set-before-migrations).

## Step 3: Generate All Service Environment Files

Run the setup script to generate a `.env` for every service from its template, substituting values from the root `.env`:

**Linux / macOS / WSL:**
```bash
./scripts/setup-env.sh
```

**Windows (PowerShell or CMD):**
```bash
bash ./scripts/setup-env.sh
```

This creates:
- `infrastructure/databases/migrations/postgres/alembic/.env`
- `services/auth-service/.env`
- `services/platform-core-service/.env`
- `services/inference-service/.env`
- `frontend/simple-ui/.env`

Re-run this script any time you change the root `.env`.

## Step 4: Start Infrastructure Services

### Option A: Minimal (recommended)

Only `postgres` and `redis` are required. The Next.js API proxy (`src/pages/api/v1/[...proxy].ts`) handles all `/api/v1/…` routing, forward-auth, and header injection directly — the three FastAPI services and the Simple UI run natively:

```bash
docker compose -f docker-compose-local.yml up -d postgres redis
```

### Option B: Full observability stack

Adds Kafka (trace transport), OpenSearch (trace/log storage), Prometheus, Grafana, and Alertmanager. These services are profile-gated in the compose file; pass `--profile` flags to activate them:

```bash
docker compose -f docker-compose-local.yml \
  --profile logging --profile observability \
  up -d \
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

## Step 5: Initialize Databases

The platform uses Alembic for database migrations. Run them from the host using the CLI wrapper (`infrastructure/databases/cli.py`). For full details see [`infrastructure/databases/MIGRATIONS.md`](../infrastructure/databases/MIGRATIONS.md).

### Step 5.1: Install Migration Framework Dependencies

**Linux/macOS/WSL:**
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
  - Service configurations and default alert rules — including any `TRITON_ENDPOINT_*` values set in [Step 2](#step-2-create-the-root-environment-file)

**Note:** Re-running `./scripts/migrate.sh all upgrade` is the way to re-apply seed data. There is no separate seed step.

## Step 6: Auth Service

The auth service handles authentication, authorization, RBAC, API keys, and JWT issuance. See [`services/auth-service/README.md`](../services/auth-service/README.md) and [`docs/architecture/01-auth-service.md`](architecture/01-auth-service.md) for full details.

### Step 6.1: Install Dependencies and Run

**Linux/macOS/WSL:**
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

> **This command runs in the foreground and keeps the terminal occupied.** Leave it running and open a **new terminal** for the next step. When you need to stop the service, press `Ctrl+C` — then run `deactivate && cd ../..` to exit the virtualenv and return to the repo root.

## Step 7: Platform Core Service

The platform core service is the model and service registry, alert management, and telemetry query API. See [`services/platform-core-service/README.md`](../services/platform-core-service/README.md) and [`docs/architecture/02-platform-core-service.md`](architecture/02-platform-core-service.md) for full details.

### Step 7.1: Install Dependencies and Run

**Linux/macOS/WSL:**
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

> **This command runs in the foreground and keeps the terminal occupied.** Leave it running and open a **new terminal** for the next step. When you need to stop the service, press `Ctrl+C` — then run `deactivate && cd ../..` to exit the virtualenv and return to the repo root.

## Step 8: Inference Service

The inference service is the unified multi-task inference orchestration layer. See [`services/inference-service/README.md`](../services/inference-service/README.md) and [`docs/architecture/03-inference-service.md`](architecture/03-inference-service.md) for full details.

### Step 8.1: Install Dependencies and Run

**Linux/macOS/WSL:**
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

> **This command runs in the foreground and keeps the terminal occupied.** Leave it running and open a **new terminal** for the next step. When you need to stop the service, press `Ctrl+C` — then run `deactivate && cd ../..` to exit the virtualenv and return to the repo root.

## Step 9: Frontend (Simple UI)

The Simple UI is a Next.js interface for testing ASR, TTS, and NMT services. See [`frontend/simple-ui/README.md`](../frontend/simple-ui/README.md) for full details.

### Step 9.1: Install Dependencies and Run

The `setup-env.sh` script generated `frontend/simple-ui/.env` with all defaults pre-filled — no manual edits are needed. The Next.js API proxy (`src/pages/api/v1/[...proxy].ts`) handles all `/api/v1/…` routing, forward-auth, and header injection directly, proxying to the backend services (auth `:8081`, platform-core `:8095`, inference `:8090`).

> The browser only ever talks to the Next.js dev server on port 3000. To call the backend directly from curl or other non-browser clients, hit the service ports (auth `:8081`, platform-core `:8095`, inference `:8090`).

> **Windows:** Start `npm run dev` from the same WSL terminal where the backend services are running so they all share the same `localhost` network.

```bash
cd frontend/simple-ui
npm install
npm run dev
```

The UI is available at **http://localhost:3000**.

```bash
cd ../..
```

## Step 10: Configure Inference Service Endpoints (Required if not set before migrations)

Step 5's seed migration creates a service row for **every** model (NMT, ASR, OCR, NER, TTS, LLM, etc.). If you already set the relevant `TRITON_ENDPOINT_*` variables in the root `.env` back in [Step 2](#step-2-create-the-root-environment-file), those services were seeded with their endpoint already filled in — you can skip this step for them.

**If you skipped that (or need to add a service you didn't have a URL for yet), follow this step** — a seeded service with a blank `endpoint` will fail on inference calls until it's filled in. Once you have a model server (e.g. a Triton container) running and reachable, point the seeded service at it via the API.

The update call is keyed by `serviceId`, so look it up first, then patch the endpoint.

**Step 1 — `GET` the service's `serviceId`:**

```bash
curl -s "http://localhost:8095/api/v1/services?task_type=nmt" | python3 -m json.tool
```

Note the `serviceId` field for the service you want.

**Step 2 — `PATCH` the endpoint using that `serviceId`:**

```bash
curl -s -X PATCH http://localhost:8095/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "serviceId": "<serviceId-from-step-1>",
    "endpoint": "http://localhost:8000"
  }'
```

**Expected:** `{"success": true, ... "message": "Service '\''<serviceId>'\'' updated successfully."}`. This route makes a live probe request to the endpoint you pass and rejects the update if the model server doesn't respond correctly — a `400`/validation error here usually means the model server isn't reachable yet at that URL; start it and retry. No `Authorization` header is required for this call in this native setup; `X-User-Id` is optional and only recorded as the audit `updated_by` value.

## Step 11: Access the Platform

Once all services are running, use the table below to find URLs and ports.

| Service / Tool | URL | Notes |
|---|---|---|
| Auth Service | http://localhost:8081/docs | Runs natively |
| Platform Core Service | http://localhost:8095/docs | Runs natively |
| Inference Service | http://localhost:8090/docs | Runs natively |
| Simple UI | http://localhost:3000 | Runs natively (Next.js) — primary API entry point for browser clients |
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

### Frontend API calls fail (Windows)

**Symptom:** Simple UI loads at `http://localhost:3000` but API calls return errors.

**Cause:** The frontend, backend services, and Docker all need to run from the same WSL2 environment so they share the same `localhost` network.

**Fix:** Stop any services started from PowerShell/CMD, open a WSL terminal, and start everything (Docker infra, migrations, Python services, `npm run dev`) from there. Verify services are reachable:

```bash
curl http://localhost:8081/health   # auth-service
curl http://localhost:8095/health   # platform-core-service
curl http://localhost:8090/health   # inference-service
```

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

### Inference calls fail with a connection/endpoint error

**Cause:** The seeded service's `endpoint` field is blank — seed migrations don't set `TRITON_ENDPOINT_*` variables in this guide, so every service starts with no endpoint configured.

**Fix:** See [Step 10: Configure Inference Service Endpoints](#step-10-configure-inference-service-endpoints-required-if-not-set-before-migrations) — set the endpoint via `PATCH /api/v1/services` once the corresponding model server is running, or set the matching `TRITON_ENDPOINT_*` variable in the root `.env` (see [Step 2](#step-2-create-the-root-environment-file)) before your next fresh migration.

### Port conflicts

Stop the conflicting process, or change the `--port` argument when starting the affected service.

Check what is using a port:
```bash
# Linux / macOS / WSL
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
| `inference-service` | Native — python3 main.py / uvicorn | restart the terminal process |
| Simple UI (frontend) | Native — `npm run dev` | restart the terminal process |

On **Windows**, "native" means inside your **WSL2** Linux environment — the same network namespace where Docker Desktop exposes container ports.

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
