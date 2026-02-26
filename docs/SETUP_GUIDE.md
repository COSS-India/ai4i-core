# Setup Guide

This guide provides step-by-step instructions for setting up and running the AI4I Core platform.

## Prerequisites

- **[Docker](https://docs.docker.com/get-started/get-docker/)** and **[Docker Compose](https://docs.docker.com/compose/install/)** installed
- **[Git](https://git-scm.com/install/)** installed
- **[Python 3](https://www.python.org/downloads/)** and **[pip3](https://pip.pypa.io/en/stable/installation/)** installed
- At least **8GB RAM** and **20GB disk space**

## Important Note

**This guide uses `docker-compose-local.yml` for local development and testing.** All Docker Compose commands will use the `-f docker-compose-local.yml` flag to specify this configuration file.

## Step 1: Clone the Repository

```bash
git clone git@github.com:COSS-India/ai4i-core.git
cd ai4i-core
```

## Step 2: Configure Environment Variables

### Root Environment File

```bash
cp env.template .env
```

Edit `.env` if needed (defaults should work for development).

### Service Environment Files

Copy the environment template for each service and the frontend:


**Core Services**

**Core Services**
```bash
cp services/api-gateway-service/env.template services/api-gateway-service/.env
cp services/auth-service/env.template services/auth-service/.env
cp services/config-service/env.template services/config-service/.env
cp services/model-management-service/env.template services/model-management-service/.env
cp services/multi-tenant-feature/env.template services/multi-tenant-feature/.env
```


**AI/ML Services**
```bash
cp services/asr-service/env.template services/asr-service/.env
cp services/tts-service/env.template services/tts-service/.env
cp services/nmt-service/env.template services/nmt-service/.env
cp services/llm-service/env.template services/llm-service/.env
cp services/transliteration-service/env.template services/transliteration-service/.env
cp services/ocr-service/env.template services/ocr-service/.env
cp services/ner-service/env.template services/ner-service/.env
cp services/language-detection-service/env.template services/language-detection-service/.env
cp services/language-diarization-service/env.template services/language-diarization-service/.env
cp services/audio-lang-detection-service/env.template services/audio-lang-detection-service/.env
cp services/speaker-diarization-service/env.template services/speaker-diarization-service/.env
cp services/pipeline-service/env.template services/pipeline-service/.env
cp services/smr-service/env.template services/smr-service/.env
```

 **Observability Services**
```bash
cp services/alerting-service/env.template services/alerting-service/.env
cp services/dashboard-service/env.template services/dashboard-service/.env
cp services/metrics-service/env.template services/metrics-service/.env
cp services/telemetry-service/env.template services/telemetry-service/.env
```

**Frontend**
```bash
cp frontend/simple-ui/env.template frontend/simple-ui/.env
```

**Note:** You can edit these `.env` files if you need to customize settings, but the defaults should work for initial setup.

## Step 3: Build Docker Images

Build all the Docker images using the local development compose file:

```bash
docker compose -f docker-compose-local.yml build
```

**Note:** The first build may take 20-40 minutes depending on your machine and network speed. Subsequent builds will be faster due to Docker's layer caching.

## Step 4: Start Infrastructure Services

Start the infrastructure services (PostgreSQL, Redis, Kafka, etc.). Application services depend on databases being initialized:

```bash
docker compose -f docker-compose-local.yml up -d postgres redis kafka zookeeper influxdb unleash
```

Wait for all infrastructure services to be healthy:

```bash
docker compose -f docker-compose-local.yml ps
```

You should see `postgres`, `redis`, `kafka`, `zookeeper`, `influxdb`, and `unleash` all showing as "healthy" or "Up".

If any service is not running, start the specific service using: 
```bash
docker compose -f docker-compose-local.yml up -d <service-name>
```

## Step 5: Initialize Databases

The platform uses a custom Laravel-like migration framework for database management.

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

### Step 5.2: Initialize External Service Databases

External services (like Unleash) manage their own schemas. Create their databases first:

**Linux/macOS:**
```bash
python3 infrastructure/databases/cli.py init:external
```

**Windows:**
```bash
python infrastructure/databases/cli.py init:external
```

This creates the `unleash` database for the Unleash feature flag service.

### Step 5.3: Run All Migrations

Run migrations for all databases at once.

**Linux/macOS:**
```bash
python3 infrastructure/databases/cli.py migrate:all
```

**Windows:**
```bash
python infrastructure/databases/cli.py migrate:all
```

This command will:
- Create all required databases (auth_db, config_db, alerting_db, dashboard_db, metrics_db, telemetry_db, multi_tenant_db, model_management_db)
- Create all tables, indexes, constraints, and triggers
- Set up Redis cache structures
- Configure InfluxDB metrics buckets (if available)

### Step 5.4: Seed Default Data

Populate databases with default data.

**Linux/macOS:**
```bash
python3 infrastructure/databases/cli.py seed:all
```

**Windows:**
```bash
python infrastructure/databases/cli.py seed:all
```

This will create:
- Default admin user: `admin@ai4inclusion.org` / `Admin@123`
- Default roles (ADMIN, DEVELOPER, USER) and permissions
- Sample service configurations
- Default alert rules and dashboard configurations

**Note:** The migration framework automatically handles database creation, so you don't need to create databases manually.

## Step 6: Start All Services

Now that the databases are ready, start all remaining services:

```bash
docker compose -f docker-compose-local.yml up -d
```

This will start all application services, monitoring tools, and the frontend.

**Note:** Docker Compose will automatically start services in the correct order based on their dependencies.

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

Once all services are running, use the table below to find URLs and ports. The **Compose service** column gives the service name to use with Docker Compose (for example, `docker compose -f docker-compose-local.yml logs -f asr-service` or `docker compose -f docker-compose-local.yml up -d nmt-service`).

| Service / Tool | Compose service | URL | Port |
|----------------|-----------------|-----|------|
| Frontend | simple-ui-frontend | http://localhost:3000 | 3000 |
| Auth Service | auth-service | http://localhost:8081/docs | 8081 |
| Config Service | config-service | http://localhost:8082/docs | 8082 |
| Model Management Service | model-management-service | http://localhost:8094/docs | 8094 |
| ASR Service | asr-service | http://localhost:8087/docs | 8087 |
| TTS Service | tts-service | http://localhost:8088/docs | 8088 |
| NMT Service | nmt-service | http://localhost:8091/docs | 8091 |
| LLM Service | llm-service | http://localhost:8093/docs | 8093 |
| Transliteration Service | transliteration-service | http://localhost:8097/docs | 8097 |
| OCR Service | ocr-service | http://localhost:8099/docs | 8099 |
| NER Service | ner-service | http://localhost:9001/docs | 9001 |
| Language Detection Service | language-detection-service | http://localhost:8098/docs | 8098 |
| Language Diarization Service | language-diarization-service | http://localhost:9002/docs | 9002 |
| Audio Language Detection Service | audio-lang-detection-service | http://localhost:8096/docs | 8096 |
| Speaker Diarization Service | speaker-diarization-service | http://localhost:8095/docs | 8095 |
| Pipeline Service | pipeline-service | http://localhost:8092/docs | 8092 |
| Metrics Service | metrics-service | http://localhost:8083/docs | 8083 |
| Telemetry Service | telemetry-service | http://localhost:8084/docs | 8084 |
| Alerting Service | alerting-service | http://localhost:8085/docs | 8085 |
| Dashboard Service | dashboard-service | http://localhost:8090/docs | 8090 |
| API Gateway | api-gateway-service | http://localhost:9000 | 9000 |
| Prometheus | prometheus | http://localhost:9090 | 9090 |
| Grafana | grafana | http://localhost:3001 | 3001 |
| Jaeger | jaeger | http://localhost:16686 | 16686 |
| OpenSearch Dashboards | opensearch-dashboards | http://localhost:5602 | 5602 |

### Default Credentials

**Platform Admin:**
- **Username**: `admin`
- **Email**: `admin@ai4inclusion.org`
- **Password**: `Admin@123`
- **Role**: ADMIN (all permissions)

**Unleash (Feature Flags):**
- **URL**: http://localhost:4242/feature-flags
- **Username**: `admin`
- **Password**: `unleash4all`

### Before running inference

If you get a **SERVICE_UNAVAILABLE** error when calling inference (e.g. NMT, TTS, ASR), the multi-tenant service registry may not have the required services registered. See **[Multi-Tenant Service Registration](MULTI_TENANT_SERVICE_REGISTRATION.md)** for how to obtain an auth token, install curl (Windows/Linux/macOS), and register all services via the API.

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

Replace `<service-name>` with the service that is stuck (e.g. `asr-service`, `tts-service`).

Alternatively, start services in smaller groups so they come up more reliably:

```bash
docker compose -f docker-compose-local.yml up -d asr-service tts-service nmt-service
docker compose -f docker-compose-local.yml up -d llm-service pipeline-service ner-service
```

Add or repeat similar groups for other services as needed.

### Database connection errors

1. Ensure PostgreSQL is running: `docker compose -f docker-compose-local.yml ps postgres`
2. Check PostgreSQL is healthy: `docker compose -f docker-compose-local.yml ps | grep postgres`
3. Re-run migrations if needed:

   **Linux/macOS:**
   ```bash
   python3 infrastructure/databases/cli.py migrate:all
   python3 infrastructure/databases/cli.py seed:all
   ```

   **Windows:**
   ```bash
   python infrastructure/databases/cli.py migrate:all
   python infrastructure/databases/cli.py seed:all
   ```

### InfluxDB not starting

If InfluxDB fails to start or you see errors related to it, try resetting the container and volume:

```bash
docker stop ai4v-influxdb
docker rm ai4v-influxdb

docker volume ls | grep influxdb
```

Then remove the volume (replace `<VOLUME_NAME>` with the name you see, e.g. `ai4i-core_influxdb-data`):

```bash
docker volume rm <VOLUME_NAME>
```

Finally, bring InfluxDB back up:

```bash
docker compose -f docker-compose-local.yml up -d --build influxdb
```

### Postgres volume or "no such file or directory" for pg_data

The default `docker-compose-local.yml` uses a Docker-managed volume (no bind mount), so this error should not occur. If you see it, your compose file (or an override) likely uses a bind mount. Create the host directory that matches `volumes.postgres-data.driver_opts.device` in that file before starting Postgres, for example:

```bash
mkdir -p /home/ubuntu/ai4i-v/volumes/pg_data
```

Or use a path in the project: `mkdir -p volumes/pg_data` and set `device: "./volumes/pg_data"` under `postgres-data.driver_opts`.

### Default admin login not working

Use the credentials from the [Default Credentials](#default-credentials) section: **Username** `admin`, **Email** `admin@ai4inclusion.org`, **Password** `Admin@123`. 

If login still fails:

1. Check if the auth service is healthy:
   ```bash
   docker compose -f docker-compose-local.yml ps auth-service
   ```

2. Re-run the seeders to recreate the admin user:

   **Linux/macOS:**
   ```bash
   python3 infrastructure/databases/cli.py seed:all
   ```

   **Windows:**
   ```bash
   python infrastructure/databases/cli.py seed:all
   ```

3. Check auth service logs:
   ```bash
   docker compose -f docker-compose-local.yml logs auth-service
   ```

### Port conflicts

If ports are already in use, you can modify the port mappings in `docker-compose-local.yml` or stop the conflicting services.

### Inference returns SERVICE_UNAVAILABLE

If inference calls return a response like `"code": "SERVICE_UNAVAILABLE"` (e.g. "NMT service is not active at the moment"), the multi-tenant services have not been registered. Follow **[Multi-Tenant Service Registration](MULTI_TENANT_SERVICE_REGISTRATION.md)** to register the required services (tts, asr, nmt, llm, pipeline, ocr, ner, etc.) using the Register Services API.

## Architecture Notes

### Local Development Setup

This `docker-compose-local.yml` configuration is optimized for local development:

- **Direct service communication**: Services communicate directly without an API gateway layer
- **Kong API Gateway**: Not included in local setup (production only)
- **Health checks**: Configured with 6-hour intervals to reduce overhead
- **Monitoring stack**: Full observability with Prometheus, Grafana, Jaeger, and OpenSearch
- **Feature flags**: Unleash for gradual feature rollout

### Production Deployment

For production deployment with Kong API Gateway, load balancing, and enhanced security features, refer to the production docker-compose configuration.

## Next Steps

- Explore the API using Swagger documentation at http://localhost:9000/docs
- Test the frontend at http://localhost:3000
- Configure feature flags in Unleash (optional)
- Review service logs and metrics in Grafana
- Check the API documentation for detailed endpoint information

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

- **[Feature Flags](../services/config-service/docs/FEATURE_FLAGS_SETUP.md)** — Control visibility of services in the UI and create feature toggles in Unleash (e.g. `asr-enabled`, `tts-enabled`).

**Need Help?** Check the [Troubleshooting Guide](TROUBLESHOOTING.md) or open an issue on GitHub.

