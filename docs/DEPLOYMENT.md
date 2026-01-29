# Deployment Guide

## Overview
Step-by-step guide for deploying the Dhruva AI/ML Microservices Platform in development, staging, and production environments.

## Prerequisites

### System Requirements
- **CPU**: 4+ cores recommended (8+ for production)
- **RAM**: 8GB minimum (16GB+ for production)
- **Disk**: 20GB minimum (50GB+ for production)
- **OS**: Linux (Ubuntu 20.04+, CentOS 8+) or macOS

### Software Requirements
- Docker 20.10+
- Docker Compose 2.0+
- Git 2.30+
- curl (for health checks)

### Network Requirements
- Ports 3000, 8080-8089, 5432, 6379, 8086, 9200, 9092, 2181 must be available
- Internet access for pulling Docker images
- Firewall rules configured for service communication

## Development Deployment

### Step 1: Clone Repository
```bash
git clone <repository-url>
cd Ai4V-C
```

### Step 2: Configure Environment
```bash
# Copy environment template
cp env.template .env

# Edit .env file with your configuration
nano .env

# Key variables to configure:
# - POSTGRES_PASSWORD (change from default)
# - REDIS_PASSWORD (change from default)
# - JWT_SECRET_KEY (generate random string)
# - TRITON_ENDPOINT (if using external Triton server)
```

### Step 3: Configure Service-Specific Environments
```bash
# ASR Service
cp services/asr-service/env.template services/asr-service/.env

# TTS Service
cp services/tts-service/env.template services/tts-service/.env

# NMT Service
cp services/nmt-service/env.template services/nmt-service/.env

# Frontend
cp frontend/simple-ui/env.template frontend/simple-ui/.env

cp services/alerting-service/env.template services/alerting-service/.env

cp services/api-gateway-service/env.template services/api-gateway-service/.env

cp services/auth-service/env.template services/auth-service/.env

cp services/config-service/env.template services/config-service/.env

cp services/dashboard-service/env.template services/dashboard-service/.env

cp services/llm-service/env.template services/llm-service/.env

cp services/metrics-service/env.template services/metrics-service/.env

cp services/pipeline-service/env.template services/pipeline-service/.env

cp services/telemetry-service/env.template services/telemetry-service/.env

cp services/audio-lang-detection-service/env.template services/audio-lang-detection-service/.env

cp services/ner-service/env.template services/ner-service/.env
```

### Step 4: Start Infrastructure Services
```bash
# Start PostgreSQL, Redis, InfluxDB, Elasticsearch, Kafka
docker-compose up -d postgres redis influxdb elasticsearch kafka zookeeper

docker compose up -d --build postgres redis influxdb elasticsearch kafka zookeeper


# Wait for services to be healthy (30-60 seconds)
docker-compose ps
```

### Step 5: Initialize Database
```bash
# Database schemas are automatically created on first startup
# Verify database initialization
docker-compose exec postgres psql -U dhruva_user -d auth_db -c "\dt"

# Should show tables: users, api_keys, sessions, asr_requests, asr_results, tts_requests, tts_results, nmt_requests, nmt_results
```

### Step 6: Start Core Services
```bash
# Start API Gateway, Auth, Config services
docker-compose up -d api-gateway-service auth-service config-service

# Wait for services to be healthy
./scripts/health-check-all.sh
```

### Step 7: Start AI/ML Services
```bash
# Start ASR, TTS, NMT services
docker-compose up -d asr-service tts-service nmt-service

# Verify services are running
docker-compose ps | grep -E "asr|tts|nmt"
```

### Step 8: Start Frontend
```bash
# Start Simple UI
docker-compose up -d simple-ui-frontend

# Wait for build to complete (first time: 2-3 minutes)
docker-compose logs -f simple-ui-frontend
```

### Step 9: Verify Deployment
```bash
# Run comprehensive health check
./scripts/health-check-all.sh

# Expected output: All services should show "healthy"
```

### Step 10: Access Services
- **Simple UI**: http://localhost:3000
- **API Gateway**: http://localhost:8080
- **Swagger UI (ASR)**: http://localhost:8087/docs
- **Swagger UI (TTS)**: http://localhost:8088/docs
- **Swagger UI (NMT)**: http://localhost:8089/docs

## Production Deployment

### Additional Steps for Production

1. **Security Hardening**:
   - Change all default passwords in .env
   - Generate strong JWT secret keys
   - Enable HTTPS with SSL certificates
   - Configure firewall rules (allow only necessary ports)
   - Enable Docker security scanning

2. **Performance Optimization**:
   - Increase database connection pool sizes
   - Configure Redis persistence (AOF or RDB)
   - Enable database query optimization
   - Configure resource limits in docker-compose.yml

3. **High Availability**:
   - Scale services: `docker-compose up -d --scale asr-service=3`
   - Configure load balancer (nginx or HAProxy)
   - Set up database replication (PostgreSQL streaming replication)
   - Configure Redis Sentinel for failover

4. **Monitoring Setup**:
   - Configure Prometheus metrics collection
   - Set up Grafana dashboards
   - Configure alerting rules
   - Enable log aggregation to Elasticsearch

5. **Backup Strategy**:
   - Configure automated PostgreSQL backups (pg_dump)
   - Configure Redis snapshots
   - Set up backup retention policy (7 days minimum)
   - Test backup restoration procedure

## Kubernetes Deployment (Future)

### Prerequisites
- Kubernetes cluster (1.24+)
- kubectl configured
- Helm 3.0+

### Deployment Steps
1. Create namespace: `kubectl create namespace dhruva-platform`
2. Create ConfigMaps and Secrets
3. Deploy infrastructure (PostgreSQL, Redis via Helm charts)
4. Deploy microservices (use Kubernetes manifests)
5. Configure Ingress for external access
6. Set up Horizontal Pod Autoscaling (HPA)

## Rollback Procedure

### Quick Rollback
```bash
# Stop all services
./scripts/stop-all.sh

# Restore from backup
docker-compose exec postgres psql -U dhruva_user -d auth_db < backup.sql

# Start services with previous version
git checkout <previous-commit>
docker-compose up -d --build
```

## Maintenance

### Regular Maintenance Tasks
1. **Weekly**: Review logs for errors, check disk usage, verify backups
2. **Monthly**: Update Docker images, apply security patches, optimize database
3. **Quarterly**: Review and update dependencies, performance testing, capacity planning

### Updating Services
```bash
# Pull latest changes
git pull origin main

# Rebuild and restart specific service
./scripts/restart-service.sh asr-service --build

# Verify health
./scripts/health-check-all.sh
```
