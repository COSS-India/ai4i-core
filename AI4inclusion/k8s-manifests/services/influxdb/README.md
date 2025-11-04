# Influxdb Service

## Overview
Influxdb service for AI4Inclusion microservices architecture.

## Files
- `*-pvc.yaml` - Persistent Volume Claim (if applicable)
- `*-configmap.yaml` - Non-sensitive configuration
- `*-secret.yaml` - Sensitive data (passwords, API keys)
- `*-service.yaml` - Kubernetes Service
- `*-deployment.yaml` - Deployment configuration
- `deploy.sh` - Deployment script
- `cleanup.sh` - Cleanup script

## Deploy
```bash
./deploy.sh
```

## Cleanup
```bash
./cleanup.sh
```

## Check Status
```bash
kubectl get pods -n dev -l app=influxdb
kubectl get services -n dev -l app=influxdb
```

## Access
```bash
kubectl port-forward service/influxdb <port>:<port> -n dev
```
