# ASR Service - Build and Deploy Instructions

## Summary of Changes Made

The following fixes have been applied to resolve Redis connection issues:

1. **Fixed `redis_client.ping()` coroutine warning** (Line 231)
   - Removed the module-level `ping()` call that couldn't be awaited
   - Connection testing now happens in the `lifespan` function where `await` is available

2. **Configured Redis password authentication for security**
   - Redis is now configured to require password authentication
   - Created Redis ConfigMap with entrypoint script that injects password from secret
   - Updated Redis deployment to use the entrypoint script
   - ASR service secret now includes `REDIS_PASSWORD` matching Redis secret
   - Code properly handles password authentication (password is required and will be used)

3. **Made Redis password handling flexible**
   - Code checks if `REDIS_PASSWORD` is set and only passes it if not empty
   - This allows for flexibility while maintaining security by default

## Step-by-Step Build Instructions

### Prerequisites
- Docker installed and running
- AWS CLI configured with appropriate credentials
- Access to ECR repository: `662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/asr-service`
- kubectl configured to access your Kubernetes cluster

### Step 0: Deploy Redis with Password Authentication (IMPORTANT!)

**Before building the ASR service, you must deploy Redis with password authentication:**

```bash
# Navigate to Redis manifests directory
cd /home/ubuntu/AI4inclusion/k8s-manifests/services/redis

# Apply Redis ConfigMap (with entrypoint script)
kubectl apply -f redis-configmap.yaml -n dev

# Apply Redis secret (if not already applied)
kubectl apply -f redis-secret.yaml -n dev

# Update Redis deployment
kubectl apply -f redis-deployment.yaml -n dev

# Wait for Redis to be ready
kubectl rollout status deployment/redis -n dev --timeout=120s

# Verify Redis is running with password
kubectl get pods -n dev -l app=redis
```

**Note:** The Redis password is `redispass` (base64: `cmVkaXNwYXNz`). This must match the password in `asr-service-secret.yaml`.

### Step 1: Navigate to the Service Directory

```bash
cd /home/ubuntu/AI4inclusion/k8s-manifests-models/micro-services/services/asr-service
```

### Step 2: Verify Code Changes

Verify that the changes are in place:

```bash
# Check that REDIS_PASSWORD defaults to empty string
grep -n "redis_password = os.getenv" main.py

# Check that password is only passed if set
grep -n "if redis_password:" main.py

# Verify ping() is not called at module level (should not find line 231 with ping())
grep -n "redis_client.ping()" main.py
```

Expected output:
- Line 241: `redis_password = os.getenv("REDIS_PASSWORD", "")`
- Lines 63, 85, 253: `if redis_password:`
- Should NOT find `redis_client.ping()` at module level (around line 231)

### Step 3: Login to AWS ECR

```bash
# Get AWS account ID and region
AWS_ACCOUNT_ID=662074586476
AWS_REGION=ap-south-1

# Login to ECR
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
```

### Step 4: Build the Docker Image

```bash
# Build the image with a new version tag
docker build -t 662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/asr-service:v1.2 .

# Verify the image was created
docker images | grep asr-service
```

### Step 5: Test the Image Locally (Optional but Recommended)

```bash
# Run the container locally to test
docker run -d \
  --name asr-service-test \
  -p 8087:8087 \
  -e REDIS_HOST=your-redis-host \
  -e REDIS_PORT=6379 \
  -e DATABASE_URL=your-database-url \
  662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/asr-service:v1.2

# Check logs for errors
docker logs asr-service-test

# Test health endpoint
curl http://localhost:8087/health

# Stop and remove test container
docker stop asr-service-test
docker rm asr-service-test
```

### Step 6: Push Image to ECR

```bash
# Push the new image version
docker push 662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/asr-service:v1.2
```

### Step 7: Update Kubernetes Deployment

```bash
# Navigate to k8s manifests directory
cd /home/ubuntu/AI4inclusion/k8s-manifests/services/asr-service

# Update the deployment to use the new image
kubectl set image deployment/asr-service \
  asr-service=662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/asr-service:v1.2 \
  -n dev

# Or update the YAML file directly and apply
# Edit asr-service.yaml and change line 42:
#   image: 662074586476.dkr.ecr.ap-south-1.amazonaws.com/ai4voice/asr-service:v1.2
# Then apply:
kubectl apply -f asr-service.yaml -n dev
```

### Step 8: Verify Deployment

```bash
# Check deployment status
kubectl rollout status deployment/asr-service -n dev

# Get the pod name
POD_NAME=$(kubectl get pods -n dev -l app=asr-service -o jsonpath='{.items[0].metadata.name}')

# Check logs for the fixes
kubectl logs ${POD_NAME} -n dev | grep -E "(Redis|ping|AUTH)" | head -20

# Verify no more errors
kubectl logs ${POD_NAME} -n dev | grep -i "error\|warning" | grep -i "redis\|auth"
```

### Step 9: Test Health Endpoint

```bash
# Port forward to test locally
kubectl port-forward deployment/asr-service 8087:8087 -n dev

# In another terminal, test the health endpoint
curl http://localhost:8087/health

# Should return JSON with redis: "healthy" (no errors)
```

## Verification Checklist

After deployment, verify:

- [ ] No `RuntimeWarning: coroutine 'Redis.execute_command' was never awaited` warnings
- [ ] No `AUTH <password> called without any password configured` errors
- [ ] Health check shows `"redis": "healthy"`
- [ ] Service starts successfully without Redis authentication errors
- [ ] Logs show "Redis connection established successfully"

## Rollback (If Needed)

If issues occur, rollback to previous version:

```bash
kubectl rollout undo deployment/asr-service -n dev
```

## Troubleshooting

### If build fails:
- Check Docker is running: `docker ps`
- Verify you're in the correct directory with Dockerfile
- Check AWS credentials: `aws sts get-caller-identity`

### If push fails:
- Verify ECR login: `aws ecr describe-repositories --region ap-south-1`
- Check repository exists and you have push permissions

### If deployment fails:
- Check pod logs: `kubectl logs <pod-name> -n dev`
- Verify image exists in ECR: `aws ecr describe-images --repository-name ai4voice/asr-service --region ap-south-1`
- Check resource limits and node availability

