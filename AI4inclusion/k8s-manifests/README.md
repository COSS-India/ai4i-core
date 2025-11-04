# AI4Inclusion Kubernetes Manifests

This directory contains Kubernetes manifests for deploying the AI4Inclusion microservices architecture to a Kubernetes cluster.

## Architecture Overview

The application consists of:

### Infrastructure Services
- **PostgreSQL** - Primary database
- **Redis** - Caching and session storage
- **InfluxDB** - Time-series data storage
- **Elasticsearch** - Search and analytics
- **Zookeeper** - Kafka coordination
- **Kafka** - Message streaming

### Microservices
- **API Gateway** - Central entry point for all API requests
- **Auth Service** - Authentication and authorization
- **Config Service** - Configuration management
- **Metrics Service** - Metrics collection and processing
- **Telemetry Service** - Telemetry data processing
- **Alerting Service** - Alert management
- **Dashboard Service** - Analytics dashboard
- **ASR Service** - Automatic Speech Recognition
- **TTS Service** - Text-to-Speech
- **NMT Service** - Neural Machine Translation
- **Pipeline Service** - AI processing pipeline

### Frontend
- **Simple UI Frontend** - Next.js web application

## Directory Structure

```
k8s-manifests/
├── namespace.yaml                           # Dev namespace
├── deploy.sh                               # Deployment script
├── README.md                               # This file
├── infrastructure/                         # Infrastructure services
│   ├── postgres-*.yaml                     # PostgreSQL manifests
│   ├── redis-*.yaml                        # Redis manifests
│   ├── influxdb-*.yaml                     # InfluxDB manifests
│   ├── elasticsearch-*.yaml                # Elasticsearch manifests
│   ├── zookeeper-*.yaml                    # Zookeeper manifests
│   └── kafka-*.yaml                        # Kafka manifests
├── microservices/                          # Microservice manifests
│   ├── api-gateway-service/                # API Gateway
│   ├── auth-service/                       # Authentication service
│   ├── config-service/                     # Configuration service
│   ├── metrics-service/                    # Metrics service
│   ├── telemetry-service/                  # Telemetry service
│   ├── alerting-service/                   # Alerting service
│   ├── dashboard-service/                  # Dashboard service
│   ├── asr-service/                        # ASR service
│   ├── tts-service/                        # TTS service
│   ├── nmt-service/                        # NMT service
│   └── pipeline-service/                   # Pipeline service
└── frontend/                               # Frontend manifests
    └── simple-ui-frontend.yaml             # Frontend service
```

## Prerequisites

1. **Kubernetes Cluster**: A running Kubernetes cluster (local or cloud)
2. **kubectl**: Kubernetes command-line tool configured to access your cluster
3. **Docker Images**: All microservice Docker images must be built and available
4. **Storage Class**: A storage class named `standard` must be available in your cluster

## Quick Start

1. **Deploy all services**:
   ```bash
   ./deploy.sh
   ```

2. **Check deployment status**:
   ```bash
   kubectl get pods -n dev
   kubectl get services -n dev
   ```

3. **Access services**:
   ```bash
   # Frontend
   kubectl port-forward service/simple-ui-frontend 3000:3000 -n dev
   
   # API Gateway
   kubectl port-forward service/api-gateway-service 8080:8080 -n dev
   
   # Dashboard
   kubectl port-forward service/dashboard-service 8501:8501 -n dev
   ```

## Configuration

### Environment Variables

Each service has its own ConfigMap and Secret for configuration:

- **ConfigMaps**: Non-sensitive configuration data
- **Secrets**: Sensitive data (passwords, API keys, tokens)

### Persistent Volumes

All services with persistent data have PersistentVolumeClaims:

- **PostgreSQL**: 10Gi storage
- **Redis**: 5Gi storage
- **InfluxDB**: 10Gi storage
- **Elasticsearch**: 10Gi storage
- **Kafka**: 10Gi storage
- **Zookeeper**: 5Gi + 2Gi storage

### Resource Limits

Each service has resource requests and limits configured:

- **Infrastructure services**: 256Mi-1Gi memory, 200m-600m CPU
- **Microservices**: 256Mi-1Gi memory, 200m-600m CPU
- **AI services (ASR, TTS, NMT)**: 512Mi-1Gi memory, 300m-600m CPU

## Service Dependencies

The deployment script handles service dependencies:

1. **Infrastructure services** are deployed first
2. **Microservices** are deployed after infrastructure is ready
3. **Frontend** is deployed last

## Monitoring and Logs

### Check Pod Status
```bash
kubectl get pods -n dev
kubectl describe pod <pod-name> -n dev
```

### View Logs
```bash
kubectl logs -f deployment/<service-name> -n dev
```

### Check Service Status
```bash
kubectl get services -n dev
kubectl describe service <service-name> -n dev
```

## Troubleshooting

### Common Issues

1. **Pod not starting**: Check resource limits and image availability
2. **Service not accessible**: Verify service selectors and port configurations
3. **Database connection issues**: Ensure PostgreSQL is running and accessible
4. **Storage issues**: Verify storage class and PVC status

### Debug Commands

```bash
# Check pod events
kubectl get events -n dev --sort-by='.lastTimestamp'

# Check resource usage
kubectl top pods -n dev

# Check storage
kubectl get pvc -n dev

# Check service endpoints
kubectl get endpoints -n dev
```

## Scaling

To scale a service:

```bash
kubectl scale deployment <service-name> --replicas=3 -n dev
```

## Cleanup

To remove all resources:

```bash
kubectl delete namespace dev
```

## Security Considerations

1. **Secrets**: All sensitive data is stored in Kubernetes secrets
2. **Network**: Services communicate within the cluster using service names
3. **RBAC**: Consider implementing Role-Based Access Control for production
4. **Image Security**: Use trusted base images and scan for vulnerabilities

## Production Recommendations

1. **Resource Management**: Adjust resource limits based on actual usage
2. **Monitoring**: Implement comprehensive monitoring and alerting
3. **Backup**: Set up regular backups for persistent volumes
4. **Security**: Implement network policies and pod security policies
5. **High Availability**: Deploy multiple replicas for critical services
6. **Ingress**: Use an ingress controller for external access
7. **TLS**: Enable TLS for all external communications

## Support

For issues and questions:
1. Check the logs using the commands above
2. Verify all prerequisites are met
3. Ensure all Docker images are available
4. Check Kubernetes cluster resources and storage availability
