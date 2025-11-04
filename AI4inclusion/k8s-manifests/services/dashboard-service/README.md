# Dashboard Service Service

## Overview
Dashboard Service service for AI4Inclusion microservices architecture.

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
kubectl get pods -n dev -l app=dashboard-service
kubectl get services -n dev -l app=dashboard-service
```

## Access
```bash
kubectl port-forward service/dashboard-service <port>:<port> -n dev
```
