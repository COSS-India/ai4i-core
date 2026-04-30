# Kubernetes Migration Guide for Dhruva Platform

## Overview
This guide helps migrate your microservices platform from Docker Compose to Kubernetes.

## Why Kubernetes?

### Current State (Docker Compose)
✅ Fast development setup  
✅ Simple configuration  
✅ Easy to understand  
⚠️ Limited production features  
⚠️ No advanced scaling  
⚠️ No service mesh  
⚠️ Limited monitoring integration  

### Target State (Kubernetes)
✅ Production-grade orchestration  
✅ Auto-scaling (HPA, VPA)  
✅ Service mesh (Istio)  
✅ Advanced monitoring (Prometheus, Grafana)  
✅ Rolling updates & rollbacks  
✅ Multi-cloud deployment  
✅ Better resource management  
✅ Security (NetworkPolicies, RBAC)  

## Migration Strategy

### Phase 1: Infrastructure Setup (Week 1)

#### 1.1 Choose Kubernetes Platform
**Option A: Local Development**
```bash
# Using minikube
brew install minikube
minikube start

# OR using Docker Desktop
# Enable Kubernetes in Docker Desktop settings
```

**Option B: Cloud Kubernetes**
```bash
# GKE
gcloud container clusters create dhruva-cluster

# EKS  
aws eks create-cluster --name dhruva-cluster

# AKS
az aks create --resource-group dhruva-rg --name dhruva-cluster
```

#### 1.2 Install Required Tools
```bash
# kubectl
brew install kubectl

# Helm (for package management)
brew install helm

# Istioctl (for service mesh)
brew install istioctl
```

### Phase 2: Create Kubernetes Manifests (Week 2-3)

#### 2.1 Directory Structure
```
aiv4-core/
├── k8s/
│   ├── namespaces/
│   │   └── platform.yaml
│   ├── infrastructure/
│   │   ├── postgres/
│   │   ├── redis/
│   │   ├── influxdb/
│   │   ├── elasticsearch/
│   │   └── kafka/
│   ├── services/
│   │   ├── api-gateway/
│   │   ├── auth-service/
│   │   ├── asr-service/
│   │   ├── tts-service/
│   │   └── nmt-service/
│   ├── frontend/
│   │   └── simple-ui/
│   └── ingress/
│       └── nginx-ingress.yaml
```

#### 2.2 Example Service Deployment
**services/asr-service/deployment.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: asr-service
  namespace: dhruva-platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: asr-service
  template:
    metadata:
      labels:
        app: asr-service
    spec:
      containers:
      - name: asr-service
        image: dhruva/asr-service:latest
        ports:
        - containerPort: 8087
        env:
        - name: POSTGRES_HOST
          value: postgres
        - name: REDIS_HOST
          value: redis
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8087
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8087
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: asr-service
  namespace: dhruva-platform
spec:
  selector:
    app: asr-service
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8087
  type: ClusterIP
```

### Phase 3: Database Migration (Week 3)

#### PostgreSQL in Kubernetes
```bash
# Install PostgreSQL using Helm
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install postgres bitnami/postgresql \
  --namespace dhruva-platform \
  --set postgresqlPassword=your_password \
  --set postgresqlDatabase=dhruva_platform
```

#### Persistent Volumes
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: dhruva-platform
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
```

### Phase 4: Monitoring & Observability (Week 4)

#### Prometheus Operator
```bash
# Install Prometheus using Helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
```

#### Grafana Dashboards
- ASR Service metrics
- TTS Service metrics  
- NMT Service metrics
- System resource usage
- API Gateway performance

### Phase 5: Service Mesh (Week 5)

#### Install Istio
```bash
istioctl install --set profile=demo
kubectl label namespace dhruva-platform istio-injection=enabled
```

#### Service Mesh Benefits
- Automatic mTLS
- Circuit breakers
- Load balancing
- Request routing
- Traffic management

### Phase 6: Ingress & Routing (Week 5)

#### Nginx Ingress
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: dhruva-ingress
  namespace: dhruva-platform
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - api.dhruva.example.com
    secretName: dhruva-tls
  rules:
  - host: api.dhruva.example.com
    http:
      paths:
      - path: /api/v1/asr
        pathType: Prefix
        backend:
          service:
            name: asr-service
            port:
              number: 80
```

## Step-by-Step Migration Commands

### Day 1: Setup
```bash
# Create namespace
kubectl create namespace dhruva-platform

# Setup infrastructure
kubectl apply -f k8s/infrastructure/

# Wait for infrastructure to be ready
kubectl wait --for=condition=ready pod -l app=postgres -n dhruva-platform
```

### Day 2: Deploy Core Services
```bash
# Deploy API Gateway
kubectl apply -f k8s/services/api-gateway/

# Deploy Auth Service
kubectl apply -f k8s/services/auth-service/

# Deploy Config Service
kubectl apply -f k8s/services/config-service/
```

### Day 3: Deploy AI Services
```bash
# Deploy ASR Service
kubectl apply -f k8s/services/asr-service/

# Deploy TTS Service
kubectl apply -f k8s/services/tts-service/

# Deploy NMT Service
kubectl apply -f k8s/services/nmt-service/
```

### Day 4: Deploy Frontend
```bash
# Deploy Simple UI
kubectl apply -f k8s/frontend/simple-ui/
```

### Day 5: Configure Ingress
```bash
# Deploy Ingress
kubectl apply -f k8s/ingress/

# Get external IP
kubectl get ingress -n dhruva-platform
```

## Testing Migration

### Health Checks
```bash
# Check all pods
kubectl get pods -n dhruva-platform

# Check services
kubectl get svc -n dhruva-platform

# Check logs
kubectl logs -f deployment/asr-service -n dhruva-platform
```

### Load Testing
```bash
# Install k6 for load testing
brew install k6

# Run load test
k6 run load-test.js
```

## Rollback Plan

### If Migration Fails
```bash
# Keep Docker Compose running in parallel
cd aiv4-core
./scripts/start-all.sh

# Gradually migrate services one at a time
# Keep both systems running during transition
```

## Resource Requirements

### Minimum for Kubernetes
- 4 CPUs
- 8GB RAM
- 50GB Storage

### Recommended for Production
- 8+ CPUs
- 16GB+ RAM  
- 100GB+ Storage
- Multi-node cluster

## Cost Comparison

### Docker Compose (1 server)
- Server: $50-100/month
- Total: **$50-100/month**

### Kubernetes (Cloud)
- Kubernetes cluster: $0-50/month (managed)
- VMs: $150-300/month (3 nodes)
- Load balancer: $20/month
- Total: **$200-400/month**

## Next Steps

1. Start with minikube for local development
2. Create Kubernetes manifests for 1 service (ASR)
3. Test migration process
4. Gradually migrate other services
5. Setup CI/CD for K8s deployments
6. Implement monitoring and alerting

## Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Istio Documentation](https://istio.io/docs/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/)

