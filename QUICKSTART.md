# AI4I Core - Quick Start Guide

This is a quick reference for setting up the AI4I Core platform locally.

## Prerequisites

- Docker & Docker Compose
- Python 3.8+
- 8GB RAM, 20GB disk space

## Setup (5 Steps)

### 1. Clone & Configure

```bash
git clone git@github.com:COSS-India/ai4i-core.git
cd ai4i-core
cp env.template .env
```

Copy environment files for all services:
```bash
for service in api-gateway-service auth-service config-service model-management-service multi-tenant-feature asr-service tts-service nmt-service llm-service transliteration-service ocr-service ner-service language-detection-service language-diarization-service audio-lang-detection-service speaker-diarization-service pipeline-service alerting-service dashboard-service metrics-service telemetry-service; do
  cp services/$service/env.template services/$service/.env 2>/dev/null || true
done
cp frontend/simple-ui/env.template frontend/simple-ui/.env
```

### 2. Build Images

```bash
docker compose -f docker-compose-local.yml build
```

### 3. Start Infrastructure

```bash
docker compose -f docker-compose-local.yml up -d postgres redis kafka zookeeper influxdb unleash
```

### 4. Initialize Databases

```bash
cd infrastructure/databases
pip3 install -r requirements.txt
cd ../..

# Create external databases (Unleash)
python3 infrastructure/databases/cli.py init:external

# Run all migrations
python3 infrastructure/databases/cli.py migrate:all

# Seed default data
python3 infrastructure/databases/cli.py seed:all
```

### 5. Start All Services

```bash
docker compose -f docker-compose-local.yml up -d
```

## Access Points

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API Gateway | http://localhost:9000 |
| API Docs | http://localhost:9000/docs |
| Grafana | http://localhost:8097 |
| Prometheus | http://localhost:9090 |
| Jaeger | http://localhost:16686 |
| Unleash | http://localhost:4242/feature-flags |

## Default Credentials

**Admin User:**
- Email: `admin@ai4inclusion.org`
- Password: `Admin@123`

**Unleash:**
- Username: `admin`
- Password: `unleash4all`

## Quick Commands

```bash
# Check service status
docker compose -f docker-compose-local.yml ps

# View logs
docker compose -f docker-compose-local.yml logs -f [service-name]

# Restart a service
docker compose -f docker-compose-local.yml restart [service-name]

# Stop all services
docker compose -f docker-compose-local.yml down

# Stop and remove volumes
docker compose -f docker-compose-local.yml down -v
```

## Troubleshooting

**Services not healthy?**
```bash
# Check logs
docker compose -f docker-compose-local.yml logs [service-name]

# Restart service
docker compose -f docker-compose-local.yml restart [service-name]
```

**Database errors?**
```bash
# Re-run migrations
python3 infrastructure/databases/cli.py migrate:all
python3 infrastructure/databases/cli.py seed:all
```

**Login not working?**
```bash
# Check auth service
docker compose -f docker-compose-local.yml logs auth-service

# Re-seed database
python3 infrastructure/databases/cli.py seed:all
```

## Architecture

- **20+ microservices** (AI/ML, Core, Observability)
- **Direct service communication** (no API gateway overhead in local dev)
- **Full monitoring stack** (Prometheus, Grafana, Jaeger, OpenSearch)
- **Feature flags** with Unleash
- **Custom migration framework** (Laravel-style)

---

For detailed documentation, see [SETUP_GUIDE.md](docs/SETUP_GUIDE.md)
