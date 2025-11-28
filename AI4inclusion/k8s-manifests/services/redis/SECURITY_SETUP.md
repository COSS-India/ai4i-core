# Redis Security Configuration

## Overview

Redis has been configured to require password authentication for security. This ensures that only authorized services can connect to Redis.

## Configuration Details

### Password
- **Password:** `redispass`
- **Base64 encoded:** `cmVkaXNwYXNz`
- **Location:** Stored in `redis-secret` Kubernetes secret

### How It Works

1. **Redis Secret** (`redis-secret.yaml`)
   - Contains the `REDIS_PASSWORD` environment variable
   - Used by both Redis deployment and ASR service

2. **Redis ConfigMap** (`redis-configmap.yaml`)
   - Contains `redis.conf` configuration file
   - Contains `redis-entrypoint.sh` script that:
     - Reads `REDIS_PASSWORD` from environment variable
     - Injects it into `redis.conf` as `requirepass` directive
     - Starts Redis server with the configuration

3. **Redis Deployment** (`redis-deployment.yaml`)
   - Uses the entrypoint script to start Redis
   - Mounts the ConfigMap as a volume
   - Passes `REDIS_PASSWORD` from secret as environment variable

## Deployment

### Deploy Redis with Password Authentication

```bash
cd /home/ubuntu/AI4inclusion/k8s-manifests/services/redis
./deploy.sh
```

Or manually:

```bash
kubectl apply -f redis-pvc.yaml -n dev
kubectl apply -f redis-secret.yaml -n dev
kubectl apply -f redis-configmap.yaml -n dev
kubectl apply -f redis-service.yaml -n dev
kubectl apply -f redis-deployment.yaml -n dev
```

### Verify Redis is Running with Password

```bash
# Check pod status
kubectl get pods -n dev -l app=redis

# Check logs to verify password is configured
kubectl logs -n dev -l app=redis | grep -i "requirepass\|password"

# Test connection (should require password)
kubectl exec -it -n dev deployment/redis -- redis-cli
# Try: PING (should fail without AUTH)
# Then: AUTH redispass
# Then: PING (should return PONG)
```

## Service Configuration

### ASR Service Secret

The ASR service must use the same password:

```yaml
data:
  REDIS_PASSWORD: cmVkaXNwYXNz  # redispass in base64
```

This is already configured in `asr-service-secret.yaml`.

## Security Benefits

1. **Authentication Required:** Only services with the correct password can connect
2. **Secret Management:** Password is stored in Kubernetes secrets, not in code
3. **Network Security:** Even if Redis is exposed, it requires authentication
4. **Audit Trail:** All connections must authenticate, providing better logging

## Troubleshooting

### Redis won't start
- Check ConfigMap is applied: `kubectl get configmap redis-config -n dev`
- Check secret exists: `kubectl get secret redis-secret -n dev`
- Check pod logs: `kubectl logs -n dev -l app=redis`

### ASR service can't connect
- Verify `REDIS_PASSWORD` is set in `asr-service-secret`
- Verify password matches Redis secret (both should be `cmVkaXNwYXNz`)
- Check ASR service logs: `kubectl logs -n dev -l app=asr-service`

### Password mismatch
- Both Redis and ASR service must use the same password
- Password in `redis-secret.yaml` must match `asr-service-secret.yaml`
- Base64 encode: `echo -n "redispass" | base64` → `cmVkaXNwYXNz`






















