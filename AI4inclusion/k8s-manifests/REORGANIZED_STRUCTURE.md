# Reorganized Kubernetes Manifests Structure

## Overview
All manifest files have been reorganized into individual service folders for better organization and easier deployment management.

## New Directory Structure

```
k8s-manifests/
├── namespace.yaml                           # Dev namespace
├── deploy.sh                               # Main deployment script
├── cleanup.sh                              # Main cleanup script
├── STEP_BY_STEP_DEPLOYMENT.md              # Detailed deployment guide
├── QUICK_DEPLOYMENT_GUIDE.md               # Quick reference guide
├── REORGANIZED_STRUCTURE.md                # This file
└── services/                               # All services organized by folder
    ├── postgres/                           # PostgreSQL database
    │   ├── postgres-pvc.yaml
    │   ├── postgres-configmap.yaml
    │   ├── postgres-secret.yaml
    │   ├── postgres-service.yaml
    │   ├── postgres-deployment.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── redis/                              # Redis cache
    │   ├── redis-pvc.yaml
    │   ├── redis-secret.yaml
    │   ├── redis-service.yaml
    │   ├── redis-deployment.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── influxdb/                           # InfluxDB time-series DB
    │   ├── influxdb-pvc.yaml
    │   ├── influxdb-secret.yaml
    │   ├── influxdb-service.yaml
    │   ├── influxdb-deployment.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── elasticsearch/                      # Elasticsearch search engine
    │   ├── elasticsearch-pvc.yaml
    │   ├── elasticsearch-secret.yaml
    │   ├── elasticsearch-service.yaml
    │   ├── elasticsearch-deployment.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── zookeeper/                          # Zookeeper coordination
    │   ├── zookeeper-pvc.yaml
    │   ├── zookeeper-service.yaml
    │   ├── zookeeper-deployment.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── kafka/                              # Kafka message streaming
    │   ├── kafka-pvc.yaml
    │   ├── kafka-configmap.yaml
    │   ├── kafka-service.yaml
    │   ├── kafka-deployment.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── api-gateway-service/                # API Gateway
    │   ├── api-gateway-configmap.yaml
    │   ├── api-gateway-secret.yaml
    │   ├── api-gateway-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── auth-service/                       # Authentication service
    │   ├── auth-service-configmap.yaml
    │   ├── auth-service-secret.yaml
    │   ├── auth-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── config-service/                     # Configuration service
    │   ├── config-service-configmap.yaml
    │   ├── config-service-secret.yaml
    │   ├── config-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── metrics-service/                    # Metrics service
    │   ├── metrics-service-configmap.yaml
    │   ├── metrics-service-secret.yaml
    │   ├── metrics-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── telemetry-service/                  # Telemetry service
    │   ├── telemetry-service-configmap.yaml
    │   ├── telemetry-service-secret.yaml
    │   ├── telemetry-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── alerting-service/                   # Alerting service
    │   ├── alerting-service-configmap.yaml
    │   ├── alerting-service-secret.yaml
    │   ├── alerting-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── dashboard-service/                  # Dashboard service
    │   ├── dashboard-service-configmap.yaml
    │   ├── dashboard-service-secret.yaml
    │   ├── dashboard-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── asr-service/                        # ASR service
    │   ├── asr-service-configmap.yaml
    │   ├── asr-service-secret.yaml
    │   ├── asr-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── tts-service/                        # TTS service
    │   ├── tts-service-configmap.yaml
    │   ├── tts-service-secret.yaml
    │   ├── tts-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── nmt-service/                        # NMT service
    │   ├── nmt-service-configmap.yaml
    │   ├── nmt-service-secret.yaml
    │   ├── nmt-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    ├── pipeline-service/                   # Pipeline service
    │   ├── pipeline-service-configmap.yaml
    │   ├── pipeline-service-secret.yaml
    │   ├── pipeline-service.yaml
    │   ├── deploy.sh
    │   ├── cleanup.sh
    │   └── README.md
    └── simple-ui-frontend/                 # Frontend application
        ├── simple-ui-frontend.yaml
        ├── deploy.sh
        ├── cleanup.sh
        └── README.md
```

## Key Features

### ✅ Individual Service Folders
- Each service has its own dedicated folder
- All related manifests are contained within the service folder
- Easy to manage and deploy individual services

### ✅ Service-Specific Scripts
- **deploy.sh** - Deploy individual service
- **cleanup.sh** - Clean up individual service
- **README.md** - Service-specific documentation

### ✅ Deployment Options

#### Option 1: Deploy All Services (Automated)
```bash
./deploy.sh
```

#### Option 2: Deploy Individual Services
```bash
# Deploy PostgreSQL
cd services/postgres && ./deploy.sh

# Deploy API Gateway
cd services/api-gateway-service && ./deploy.sh

# Deploy Frontend
cd services/simple-ui-frontend && ./deploy.sh
```

#### Option 3: Deploy Service Dependencies
```bash
# Deploy infrastructure first
cd services/postgres && ./deploy.sh
cd services/redis && ./deploy.sh
cd services/influxdb && ./deploy.sh
cd services/elasticsearch && ./deploy.sh
cd services/zookeeper && ./deploy.sh
cd services/kafka && ./deploy.sh

# Then deploy microservices
cd services/api-gateway-service && ./deploy.sh
cd services/auth-service && ./deploy.sh
# ... and so on
```

## Service Dependencies

### Phase 1: Infrastructure Services
1. **PostgreSQL** - Primary database
2. **Redis** - Caching layer
3. **InfluxDB** - Time-series database
4. **Elasticsearch** - Search engine
5. **Zookeeper** - Kafka coordination
6. **Kafka** - Message streaming

### Phase 2: Core Microservices
7. **API Gateway** - Central entry point
8. **Auth Service** - Authentication
9. **Config Service** - Configuration management

### Phase 3: Data Processing Services
10. **Metrics Service** - Metrics collection
11. **Telemetry Service** - Telemetry processing
12. **Alerting Service** - Alert management
13. **Dashboard Service** - Analytics dashboard

### Phase 4: AI Services
14. **ASR Service** - Speech recognition
15. **TTS Service** - Text-to-speech
16. **NMT Service** - Machine translation
17. **Pipeline Service** - AI processing pipeline

### Phase 5: Frontend
18. **Simple UI Frontend** - Web application

## Benefits of New Structure

### 🎯 **Better Organization**
- Each service is self-contained
- Easy to find and manage specific services
- Clear separation of concerns

### 🚀 **Flexible Deployment**
- Deploy all services at once
- Deploy individual services
- Deploy service groups (infrastructure, microservices, etc.)

### 🔧 **Easy Maintenance**
- Update individual services without affecting others
- Debug specific services in isolation
- Scale individual services independently

### 📚 **Better Documentation**
- Service-specific README files
- Clear deployment instructions per service
- Easy to understand service dependencies

## Quick Commands

### Deploy All Services
```bash
./deploy.sh
```

### Deploy Single Service
```bash
cd services/<service-name> && ./deploy.sh
```

### Cleanup All Services
```bash
./cleanup.sh
```

### Cleanup Single Service
```bash
cd services/<service-name> && ./cleanup.sh
```

### Check Service Status
```bash
kubectl get pods -n dev
kubectl get services -n dev
```

## Total Files: 90+
- 1 namespace file
- 2 main scripts (deploy.sh, cleanup.sh)
- 4 documentation files
- 18 service folders
- 18 service-specific deploy scripts
- 18 service-specific cleanup scripts
- 18 service-specific README files
- 58 Kubernetes manifest files

This reorganized structure provides maximum flexibility and ease of management for your Kubernetes microservices deployment!
