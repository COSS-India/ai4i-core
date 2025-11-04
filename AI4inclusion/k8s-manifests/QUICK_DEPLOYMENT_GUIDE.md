# Quick Deployment Guide

## Deploy All Services (Automated)
```bash
./deploy.sh
```

## Deploy Individual Services

### Infrastructure Services
```bash
# PostgreSQL
cd services/postgres && ./deploy.sh

# Redis
cd services/redis && ./deploy.sh

# InfluxDB
cd services/influxdb && ./deploy.sh

# Elasticsearch
cd services/elasticsearch && ./deploy.sh

# Zookeeper
cd services/zookeeper && ./deploy.sh

# Kafka
cd services/kafka && ./deploy.sh
```

### Microservices
```bash
# API Gateway
cd services/api-gateway-service && ./deploy.sh

# Auth Service
cd services/auth-service && ./deploy.sh

# Config Service
cd services/config-service && ./deploy.sh

# Metrics Service
cd services/metrics-service && ./deploy.sh

# Telemetry Service
cd services/telemetry-service && ./deploy.sh

# Alerting Service
cd services/alerting-service && ./deploy.sh

# Dashboard Service
cd services/dashboard-service && ./deploy.sh

# ASR Service
cd services/asr-service && ./deploy.sh

# TTS Service
cd services/tts-service && ./deploy.sh

# NMT Service
cd services/nmt-service && ./deploy.sh

# Pipeline Service
cd services/pipeline-service && ./deploy.sh
```

### Frontend
```bash
# Frontend
cd services/simple-ui-frontend && ./deploy.sh
```

## Cleanup Individual Services
```bash
# Example: Clean up PostgreSQL
cd services/postgres && ./cleanup.sh

# Example: Clean up API Gateway
cd services/api-gateway-service && ./cleanup.sh
```

## Check Service Status
```bash
# Check all pods
kubectl get pods -n dev

# Check specific service
kubectl get pods -n dev -l app=postgres
kubectl get services -n dev -l app=postgres
```

## Access Services
```bash
# Frontend
kubectl port-forward service/simple-ui-frontend 3000:3000 -n dev

# API Gateway
kubectl port-forward service/api-gateway-service 8080:8080 -n dev

# Dashboard
kubectl port-forward service/dashboard-service 8501:8501 -n dev
```

## Service Dependencies

Deploy in this order for proper dependencies:

1. **Namespace** → `kubectl apply -f namespace.yaml`
2. **PostgreSQL** → `cd services/postgres && ./deploy.sh`
3. **Redis** → `cd services/redis && ./deploy.sh`
4. **InfluxDB** → `cd services/influxdb && ./deploy.sh`
5. **Elasticsearch** → `cd services/elasticsearch && ./deploy.sh`
6. **Zookeeper** → `cd services/zookeeper && ./deploy.sh`
7. **Kafka** → `cd services/kafka && ./deploy.sh`
8. **API Gateway** → `cd services/api-gateway-service && ./deploy.sh`
9. **Auth Service** → `cd services/auth-service && ./deploy.sh`
10. **Config Service** → `cd services/config-service && ./deploy.sh`
11. **Metrics Service** → `cd services/metrics-service && ./deploy.sh`
12. **Telemetry Service** → `cd services/telemetry-service && ./deploy.sh`
13. **Alerting Service** → `cd services/alerting-service && ./deploy.sh`
14. **Dashboard Service** → `cd services/dashboard-service && ./deploy.sh`
15. **ASR Service** → `cd services/asr-service && ./deploy.sh`
16. **TTS Service** → `cd services/tts-service && ./deploy.sh`
17. **NMT Service** → `cd services/nmt-service && ./deploy.sh`
18. **Pipeline Service** → `cd services/pipeline-service && ./deploy.sh`
19. **Frontend** → `cd services/simple-ui-frontend && ./deploy.sh`
