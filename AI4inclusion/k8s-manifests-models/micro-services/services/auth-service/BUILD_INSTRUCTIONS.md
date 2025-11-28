# Auth Service - Build and Deploy Instructions

## Summary of Changes Made

The following fixes have been applied to resolve Redis connection issues and add readiness endpoint:

1. **Fixed Redis connection handling**
   - Made Redis password optional (only include if set)
   - Added retry logic with backoff for Redis connection attempts
   - Handle connection failures gracefully

2. **Updated Redis configuration**
   - Updated ConfigMap to use FQDN: `redis.dev.svc.cluster.local`
   - Updated Secret to use correct Redis password: `redispass`

3. **Added `/ready` endpoint**
   - Added readiness check endpoint for Kubernetes probes
   - Checks PostgreSQL connectivity (required for readiness)

## Why `/ready` Returns 404

The `/ready` endpoint was added to the source code (`main.py`), but the Docker image currently running (`v1.1`) was built **before** this change. You need to rebuild and push a new Docker image for the endpoint to be available.

## Step-by-Step Build Instructions

### Prerequisites
- Docker installed and running
- AWS CLI configured with appropriate credentials
- Access to ECR repository: `662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/auth-service`
- kubectl configured to access your Kubernetes cluster

### Step 0: Verify Redis is Running with Password (IMPORTANT!)

**Before building the auth service, ensure Redis is deployed with password authentication:**

```bash
# Check Redis is running
kubectl get pods -n dev -l app=redis

# Verify Redis has password configured
kubectl logs -n dev -l app=redis | grep -i "requirepass"
```

### Step 1: Navigate to Auth Service Directory

```bash
cd /home/ubuntu/AI4inclusion/k8s-manifests-models/micro-services/services/auth-service
```

### Step 2: Build Docker Image

```bash
# Build the image with a new tag (e.g., v1.2)
docker build -t 662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/auth-service:v1.2 .

# Verify the image was built
docker images | grep auth-service
```

### Step 3: Login to AWS ECR

```bash
# Login to ECR
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 662074586476.dkr.ecr.ap-south-1.amazonaws.com
```

### Step 4: Push Image to ECR

```bash
# Push the new image
docker push 662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/auth-service:v1.2
```

### Step 5: Update Kubernetes Deployment

```bash
# Update the deployment to use the new image
kubectl set image deployment/auth-service auth-service=662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/auth-service:v1.2 -n dev

# Or update the YAML file and apply
# Edit k8s-manifests/services/auth-service/auth-service.yaml
# Change: image: 662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/auth-service:v1.2
# Then: kubectl apply -f k8s-manifests/services/auth-service/auth-service.yaml -n dev
```

### Step 6: Wait for Rollout

```bash
# Wait for the new deployment to be ready
kubectl rollout status deployment/auth-service -n dev --timeout=120s
```

### Step 7: Verify Deployment

```bash
# Check pod status
kubectl get pods -n dev -l app=auth-service

# Check logs for successful startup
kubectl logs -n dev -l app=auth-service --tail=50

# Test /ready endpoint
POD_NAME=$(kubectl get pods -n dev -l app=auth-service --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD_NAME -n dev -- curl -s http://localhost:8081/ready | python3 -m json.tool

# Test /health endpoint
kubectl exec $POD_NAME -n dev -- curl -s http://localhost:8081/health | python3 -m json.tool
```

### Step 8: Verify Readiness Probe

```bash
# Check if the pod is ready (should show 1/1 READY)
kubectl get pods -n dev -l app=auth-service

# Check pod events
kubectl describe pod -n dev -l app=auth-service | grep -A 5 "Events:"
```

## Troubleshooting

### If `/ready` still returns 404:
1. Verify the new image was pushed successfully
2. Check that the deployment is using the new image tag
3. Verify the pod is running the new image: `kubectl describe pod -n dev -l app=auth-service | grep Image:`

### If Redis connection fails:
1. Verify Redis is running: `kubectl get pods -n dev -l app=redis`
2. Check Redis logs: `kubectl logs -n dev -l app=redis`
3. Verify the secret has the correct password: `kubectl get secret auth-service-secrets -n dev -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d`

### If PostgreSQL connection fails:
1. Verify PostgreSQL is running: `kubectl get pods -n dev -l app=postgres`
2. Check the DATABASE_URL in the secret matches your PostgreSQL configuration

## Quick Build Script

You can also use this one-liner to build and push (replace v1.2 with your desired version):

```bash
cd /home/ubuntu/AI4inclusion/k8s-manifests-models/micro-services/services/auth-service && \
docker build -t 662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/auth-service:v1.2 . && \
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 662074586476.dkr.ecr.ap-south-1.amazonaws.com && \
docker push 662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/auth-service:v1.2 && \
kubectl set image deployment/auth-service auth-service=662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/auth-service:v1.2 -n dev
```






















