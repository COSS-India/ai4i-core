# Zookeeper Service

## Overview
Zookeeper service for AI4Inclusion microservices architecture.

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
kubectl get pods -n dev -l app=zookeeper
kubectl get services -n dev -l app=zookeeper
```

## Access
```bash
kubectl port-forward service/zookeeper <port>:<port> -n dev
```
