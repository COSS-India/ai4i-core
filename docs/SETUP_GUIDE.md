# Setup Guide

This guide provides step-by-step instructions for setting up and running the AI4I Core platform.

## Prerequisites

- **[Docker](https://docs.docker.com/get-started/get-docker/)** and **[Docker Compose](https://docs.docker.com/compose/install/)** installed
- **[Git](https://git-scm.com/install/)** installed
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

```bash
# Core Services
cp services/api-gateway-service/env.template services/api-gateway-service/.env
cp services/auth-service/env.template services/auth-service/.env
cp services/config-service/env.template services/config-service/.env
cp services/model-management-service/env.template services/model-management-service/.env
cp services/multi-tenant-feature/env.template services/multi-tenant-feature/.env

# AI/ML Services
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

# Observability Services
cp services/alerting-service/env.template services/alerting-service/.env
cp services/dashboard-service/env.template services/dashboard-service/.env
cp services/metrics-service/env.template services/metrics-service/.env
cp services/telemetry-service/env.template services/telemetry-service/.env

# Frontend
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

## Step 5: Initialize Database

Run the database initialization script to create all databases and tables. You can use any of these methods:

**Method 1 (Recommended - using wrapper script):**

```bash
./infrastructure/postgres/init-all-databases.sh
```

**Note:** If you get a "permission denied" error, you can run it with `bash`:
```bash
bash infrastructure/postgres/init-all-databases.sh
```

**Method 2 (Direct SQL execution):**

```bash
docker compose -f docker-compose-local.yml exec postgres psql -U dhruva_user -d dhruva_platform -f /docker-entrypoint-initdb.d/init-all-databases.sql
```

**Method 3 (Alternative - copy file first):**

If Method 2 doesn't work, copy the file into the container and run it:

```bash
docker compose -f docker-compose-local.yml cp infrastructure/postgres/init-all-databases.sql postgres:/tmp/init-all-databases.sql
docker compose -f docker-compose-local.yml exec postgres psql -U dhruva_user -d dhruva_platform -f /tmp/init-all-databases.sql
```

**Note:** The SQL file `infrastructure/postgres/init-all-databases.sql` contains everything needed to set up all databases, tables, and seed data in a single execution. The script now handles existing databases gracefully (errors are ignored if databases already exist).

This script will:
- Create all required databases (auth_db, config_db, model_management_db, unleash)
- Create all tables and schemas
- Set up indexes and triggers
- Insert seed data (default admin user, roles, permissions, etc.)

## Step 6: Start Application Services

Now that the databases are ready, start all application services:

```bash
docker compose -f docker-compose-local.yml up -d \
  api-gateway-service \
  auth-service \
  config-service \
  model-management-service \
  asr-service \
  tts-service \
  nmt-service \
  llm-service \
  transliteration-service \
  ocr-service \
  ner-service \
  language-detection-service \
  language-diarization-service \
  audio-lang-detection-service \
  speaker-diarization-service \
  pipeline-service \
  metrics-service \
  telemetry-service \
  alerting-service \
  dashboard-service \
  simple-ui-frontend
```

Check that all services are running:

```bash
docker compose -f docker-compose-local.yml ps
```

All services should show as "Up" or "healthy".

## Step 7: Access the Platform

Once all services are running, you can access:

### Frontend & API

- **Simple UI Frontend**: http://localhost:3000
- **API Gateway**: http://localhost:8080
- **API Gateway Swagger**: http://localhost:8080/docs

### Service Swagger Documentation

#### Core Services
| Service | URL | Port |
|---------|-----|------|
| API Gateway | http://localhost:8080/docs | 8080 |
| Auth Service | http://localhost:8081/docs | 8081 |
| Config Service | http://localhost:8082/docs | 8082 |
| Model Management Service | http://localhost:8094/docs | 8094 |

#### AI/ML Services
| Service | URL | Port |
|---------|-----|------|
| ASR Service | http://localhost:8087/docs | 8087 |
| TTS Service | http://localhost:8088/docs | 8088 |
| NMT Service | http://localhost:8091/docs | 8091 |
| LLM Service | http://localhost:8093/docs | 8093 |
| Transliteration Service | http://localhost:8097/docs | 8097 |
| OCR Service | http://localhost:8099/docs | 8099 |
| NER Service | http://localhost:9001/docs | 9001 |
| Language Detection Service | http://localhost:8098/docs | 8098 |
| Language Diarization Service | http://localhost:9002/docs | 9002 |
| Audio Language Detection Service | http://localhost:8096/docs | 8096 |
| Speaker Diarization Service | http://localhost:8095/docs | 8095 |
| Pipeline Service | http://localhost:8092/docs | 8092 |

#### Observability Services
| Service | URL | Port |
|---------|-----|------|
| Metrics Service | http://localhost:8083/docs | 8083 |
| Telemetry Service | http://localhost:8084/docs | 8084 |
| Alerting Service | http://localhost:8085/docs | 8085 |
| Dashboard Service | http://localhost:8090/docs | 8090 |

### Default Credentials

- **Admin User**: `admin@ai4i.com`
- **Password**: `admin123`

## Troubleshooting

### Services not starting

1. Check logs: `docker compose -f docker-compose-local.yml logs <service-name>`
2. Verify environment files exist in each service directory
3. Check if ports are already in use: `netstat -tulpn | grep <port>`

### Database connection errors

1. Ensure PostgreSQL is running: `docker compose -f docker-compose-local.yml ps postgres`
2. Wait a few seconds after starting services for databases to initialize
3. Re-run the database initialization script if needed

### Port conflicts

If ports are already in use, you can modify the port mappings in `docker-compose-local.yml` or stop the conflicting services.

## Next Steps

- Explore the API using Swagger documentation
- Test the frontend at http://localhost:3000
- Review the [API Documentation](API_DOCUMENTATION.md) for detailed endpoint information
- Check [Deployment Guide](DEPLOYMENT.md) for production setup

## Stopping Services

To stop all services:

```bash
docker compose -f docker-compose-local.yml down
```

To stop and remove all data (volumes):

```bash
docker compose -f docker-compose-local.yml down -v
```

## Optional: Feature Flags Configuration

The UI is integrated with feature flags to conditionally show/hide service features. If you want to control the visibility of services in the UI, you can create the following feature flags in Unleash:

### Feature Flags Integrated with UI

The following feature flags are used by the frontend to control service visibility:

- **`asr-enabled`** - Controls visibility of ASR (Automatic Speech Recognition) service
- **`tts-enabled`** - Controls visibility of TTS (Text-to-Speech) service
- **`nmt-enabled`** - Controls visibility of NMT (Neural Machine Translation) service
- **`llm-enabled`** - Controls visibility of LLM (Large Language Model) service
- **`pipeline-enabled`** - Controls visibility of Pipeline service

### How to Create Feature Flags in Unleash

1. **Access Unleash UI**: 
   - **Local Development**: Navigate to http://localhost:4242/feature-flags
   - **Default Username**: `admin`
   - **Default Password**: `unleash4all`

2. **Create a Feature Flag**:
   - Click "Create feature toggle"
   - Enter the flag name (e.g., `asr-enabled`)
   - Add a description (optional)
   - Select flag type: `release` (recommended)
   - Click "Create feature toggle"

3. **Configure Environment Settings**:
   - Enable or disable the flag for each environment (development, staging, production)
   - Add targeting strategies if needed (gradual rollout, user targeting, etc.)

4. **Repeat** for each flag you want to configure

### Behavior

- **If a flag exists and is enabled**: The corresponding service will be visible in the UI
- **If a flag exists and is disabled**: The corresponding service will be hidden in the UI
- **If a flag doesn't exist**: The service will be visible by default

**Note**: Feature flags are completely optional. If you don't create them, all services will be visible in the UI by default. Only create flags if you need to control service visibility.

---

**Need Help?** Check the [Troubleshooting Guide](TROUBLESHOOTING.md) or open an issue on GitHub.

