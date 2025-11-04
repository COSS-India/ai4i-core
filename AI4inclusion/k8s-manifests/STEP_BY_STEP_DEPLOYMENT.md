# AI4Inclusion Step-by-Step Deployment Guide

This guide provides detailed instructions for deploying each service individually in the correct order.

## Prerequisites

1. **Kubernetes cluster** running and accessible
2. **kubectl** configured to access your cluster
3. **Docker images** built and available in your registry
4. **Storage class** named `standard` available in your cluster

## Directory Structure

```
k8s-manifests/
├── namespace.yaml                    # Dev namespace
├── services/                         # All services organized by folder
│   ├── postgres/                    # PostgreSQL database
│   ├── redis/                       # Redis cache
│   ├── influxdb/                    # InfluxDB time-series DB
│   ├── elasticsearch/               # Elasticsearch search engine
│   ├── zookeeper/                   # Zookeeper coordination
│   ├── kafka/                       # Kafka message streaming
│   ├── api-gateway-service/         # API Gateway
│   ├── auth-service/                # Authentication service
│   ├── config-service/              # Configuration service
│   ├── metrics-service/             # Metrics service
│   ├── telemetry-service/           # Telemetry service
│   ├── alerting-service/            # Alerting service
│   ├── dashboard-service/           # Dashboard service
│   ├── asr-service/                 # ASR service
│   ├── tts-service/                 # TTS service
│   ├── nmt-service/                 # NMT service
│   ├── pipeline-service/            # Pipeline service
│   └── simple-ui-frontend/          # Frontend application
├── deploy.sh                        # Automated deployment script
├── cleanup.sh                       # Cleanup script
└── README.md                        # Documentation
```

## Deployment Order

### Phase 1: Namespace and Infrastructure Services

#### Step 1: Create Namespace
```bash
kubectl apply -f namespace.yaml
```

#### Step 2: Deploy PostgreSQL
```bash
cd services/postgres
kubectl apply -f postgres-pvc.yaml
kubectl apply -f postgres-configmap.yaml
kubectl apply -f postgres-secret.yaml
kubectl apply -f postgres-service.yaml
kubectl apply -f postgres-deployment.yaml

# Wait for PostgreSQL to be ready
kubectl wait --for=condition=available --timeout=300s deployment/postgres -n dev
kubectl get pods -n dev -l app=postgres
```

#### Step 3: Deploy Redis
```bash
cd ../redis
kubectl apply -f redis-pvc.yaml
kubectl apply -f redis-secret.yaml
kubectl apply -f redis-service.yaml
kubectl apply -f redis-deployment.yaml

# Wait for Redis to be ready
kubectl wait --for=condition=available --timeout=300s deployment/redis -n dev
kubectl get pods -n dev -l app=redis
```

#### Step 4: Deploy InfluxDB
```bash
cd ../influxdb
kubectl apply -f influxdb-pvc.yaml
kubectl apply -f influxdb-secret.yaml
kubectl apply -f influxdb-service.yaml
kubectl apply -f influxdb-deployment.yaml

# Wait for InfluxDB to be ready
kubectl wait --for=condition=available --timeout=300s deployment/influxdb -n dev
kubectl get pods -n dev -l app=influxdb
```

#### Step 5: Deploy Elasticsearch
```bash
cd ../elasticsearch
kubectl apply -f elasticsearch-pvc.yaml
kubectl apply -f elasticsearch-secret.yaml
kubectl apply -f elasticsearch-service.yaml
kubectl apply -f elasticsearch-deployment.yaml

# Wait for Elasticsearch to be ready
kubectl wait --for=condition=available --timeout=300s deployment/elasticsearch -n dev
kubectl get pods -n dev -l app=elasticsearch
```

#### Step 6: Deploy Zookeeper
```bash
cd ../zookeeper
kubectl apply -f zookeeper-pvc.yaml
kubectl apply -f zookeeper-service.yaml
kubectl apply -f zookeeper-deployment.yaml

# Wait for Zookeeper to be ready
kubectl wait --for=condition=available --timeout=300s deployment/zookeeper -n dev
kubectl get pods -n dev -l app=zookeeper
```

#### Step 7: Deploy Kafka
```bash
cd ../kafka
kubectl apply -f kafka-pvc.yaml
kubectl apply -f kafka-configmap.yaml
kubectl apply -f kafka-service.yaml
kubectl apply -f kafka-deployment.yaml

# Wait for Kafka to be ready
kubectl wait --for=condition=available --timeout=300s deployment/kafka -n dev
kubectl get pods -n dev -l app=kafka
```

### Phase 2: Core Microservices

#### Step 8: Deploy API Gateway Service
```bash
cd ../api-gateway-service
kubectl apply -f api-gateway-configmap.yaml
kubectl apply -f api-gateway-secret.yaml
kubectl apply -f api-gateway-service.yaml

# Wait for API Gateway to be ready
kubectl wait --for=condition=available --timeout=300s deployment/api-gateway-service -n dev
kubectl get pods -n dev -l app=api-gateway-service
```

#### Step 9: Deploy Auth Service
```bash
cd ../auth-service
kubectl apply -f auth-service-configmap.yaml
kubectl apply -f auth-service-secret.yaml
kubectl apply -f auth-service.yaml

# Wait for Auth Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/auth-service -n dev
kubectl get pods -n dev -l app=auth-service
```

#### Step 10: Deploy Config Service
```bash
cd ../config-service
kubectl apply -f config-service-configmap.yaml
kubectl apply -f config-service-secret.yaml
kubectl apply -f config-service.yaml

# Wait for Config Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/config-service -n dev
kubectl get pods -n dev -l app=config-service
```

### Phase 3: Data Processing Services

#### Step 11: Deploy Metrics Service
```bash
cd ../metrics-service
kubectl apply -f metrics-service-configmap.yaml
kubectl apply -f metrics-service-secret.yaml
kubectl apply -f metrics-service.yaml

# Wait for Metrics Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/metrics-service -n dev
kubectl get pods -n dev -l app=metrics-service
```

#### Step 12: Deploy Telemetry Service
```bash
cd ../telemetry-service
kubectl apply -f telemetry-service-configmap.yaml
kubectl apply -f telemetry-service-secret.yaml
kubectl apply -f telemetry-service.yaml

# Wait for Telemetry Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/telemetry-service -n dev
kubectl get pods -n dev -l app=telemetry-service
```

#### Step 13: Deploy Alerting Service
```bash
cd ../alerting-service
kubectl apply -f alerting-service-configmap.yaml
kubectl apply -f alerting-service-secret.yaml
kubectl apply -f alerting-service.yaml

# Wait for Alerting Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/alerting-service -n dev
kubectl get pods -n dev -l app=alerting-service
```

#### Step 14: Deploy Dashboard Service
```bash
cd ../dashboard-service
kubectl apply -f dashboard-service-configmap.yaml
kubectl apply -f dashboard-service-secret.yaml
kubectl apply -f dashboard-service.yaml

# Wait for Dashboard Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/dashboard-service -n dev
kubectl get pods -n dev -l app=dashboard-service
```

### Phase 4: AI Services

#### Step 15: Deploy ASR Service
```bash
cd ../asr-service
kubectl apply -f asr-service-configmap.yaml
kubectl apply -f asr-service-secret.yaml
kubectl apply -f asr-service.yaml

# Wait for ASR Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/asr-service -n dev
kubectl get pods -n dev -l app=asr-service
```

#### Step 16: Deploy TTS Service
```bash
cd ../tts-service
kubectl apply -f tts-service-configmap.yaml
kubectl apply -f tts-service-secret.yaml
kubectl apply -f tts-service.yaml

# Wait for TTS Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/tts-service -n dev
kubectl get pods -n dev -l app=tts-service
```

#### Step 17: Deploy NMT Service
```bash
cd ../nmt-service
kubectl apply -f nmt-service-configmap.yaml
kubectl apply -f nmt-service-secret.yaml
kubectl apply -f nmt-service.yaml

# Wait for NMT Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/nmt-service -n dev
kubectl get pods -n dev -l app=nmt-service
```

#### Step 18: Deploy Pipeline Service
```bash
cd ../pipeline-service
kubectl apply -f pipeline-service-configmap.yaml
kubectl apply -f pipeline-service-secret.yaml
kubectl apply -f pipeline-service.yaml

# Wait for Pipeline Service to be ready
kubectl wait --for=condition=available --timeout=300s deployment/pipeline-service -n dev
kubectl get pods -n dev -l app=pipeline-service
```

### Phase 5: Frontend

#### Step 19: Deploy Frontend
```bash
cd ../simple-ui-frontend
kubectl apply -f simple-ui-frontend.yaml

# Wait for Frontend to be ready
kubectl wait --for=condition=available --timeout=300s deployment/simple-ui-frontend -n dev
kubectl get pods -n dev -l app=simple-ui-frontend
```

## Verification

### Check All Services Status
```bash
# Check all pods
kubectl get pods -n dev

# Check all services
kubectl get services -n dev

# Check all persistent volume claims
kubectl get pvc -n dev
```

### Access Services
```bash
# Frontend
kubectl port-forward service/simple-ui-frontend 3000:3000 -n dev

# API Gateway
kubectl port-forward service/api-gateway-service 8080:8080 -n dev

# Dashboard
kubectl port-forward service/dashboard-service 8501:8501 -n dev
```

## Troubleshooting

### Check Service Logs
```bash
# Check logs for any service
kubectl logs -f deployment/<service-name> -n dev

# Example: Check API Gateway logs
kubectl logs -f deployment/api-gateway-service -n dev
```

### Check Service Health
```bash
# Describe a pod to see events
kubectl describe pod <pod-name> -n dev

# Check service endpoints
kubectl get endpoints -n dev
```

### Common Issues

1. **Pod not starting**: Check resource limits and image availability
2. **Service not accessible**: Verify service selectors and port configurations
3. **Database connection issues**: Ensure PostgreSQL is running and accessible
4. **Storage issues**: Verify storage class and PVC status

## Quick Commands

### Deploy All Services (Automated)
```bash
./deploy.sh
```

### Deploy Single Service
```bash
# Example: Deploy only PostgreSQL
cd services/postgres
kubectl apply -f .
```

### Check Service Status
```bash
kubectl get pods -n dev -l app=<service-name>
```

### Delete Single Service
```bash
# Example: Delete only PostgreSQL
cd services/postgres
kubectl delete -f .
```

### Cleanup All Services
```bash
./cleanup.sh
```

## Service Dependencies

- **PostgreSQL** → Auth Service, Config Service, Metrics Service, Telemetry Service, Alerting Service, Dashboard Service, ASR Service, TTS Service, NMT Service, Pipeline Service
- **Redis** → All microservices
- **InfluxDB** → Metrics Service, Dashboard Service
- **Elasticsearch** → Telemetry Service
- **Kafka** → Config Service, Telemetry Service, Alerting Service
- **Zookeeper** → Kafka
- **ASR Service** → Pipeline Service
- **NMT Service** → Pipeline Service
- **TTS Service** → Pipeline Service
- **API Gateway** → Frontend

## Notes

- Each service folder contains all necessary manifests (PVC, ConfigMap, Secret, Service, Deployment)
- Services are deployed in dependency order
- Each step includes verification commands
- All services use the `dev` namespace
- Persistent volumes ensure data persistence across pod restarts
