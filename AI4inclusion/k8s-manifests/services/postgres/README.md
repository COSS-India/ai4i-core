# PostgreSQL Service

## Overview
PostgreSQL database service for AI4Inclusion microservices architecture.

## Files
- `postgres-pvc.yaml` - Persistent Volume Claim (10Gi)
- `postgres-configmap.yaml` - Non-sensitive configuration
- `postgres-secret.yaml` - Sensitive data (passwords)
- `postgres-service.yaml` - Kubernetes Service
- `postgres-deployment.yaml` - Deployment configuration
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
kubectl get pods -n dev -l app=postgres
kubectl get services -n dev -l app=postgres
```

## Access
```bash
kubectl port-forward service/postgres 5432:5432 -n dev
```

## Configuration
- **Database**: ai4v_db
- **User**: ai4v_user
- **Password**: password123 (base64 encoded)
- **Port**: 5432
- **Storage**: 10Gi persistent volume
