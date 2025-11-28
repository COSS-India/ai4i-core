# ASR Service - Changes Summary

## Issues Fixed

### 1. RuntimeWarning: coroutine 'Redis.execute_command' was never awaited
**Location:** Line 231 in `main.py`  
**Problem:** `redis_client.ping()` was called at module level without `await`  
**Fix:** Removed the module-level `ping()` call. Connection testing now happens in the `lifespan` function where `await` is available.

### 2. Redis Authentication Error
**Error:** `AUTH <password> called without any password configured for the default user`  
**Problem:** Code was trying to authenticate with a password when Redis doesn't have one configured  
**Fix:** 
- Configured Redis to require password authentication for security
- Created Redis ConfigMap with entrypoint script that injects password from secret
- Updated Redis deployment to use password authentication
- ASR service now uses the same password from secret
- Code properly handles password authentication

## Code Changes Made

### File: `main.py`

#### Change 1: Module-level Redis initialization (Lines 236-263)
**Before:**
```python
redis_password = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")

redis_client = redis.Redis(
    host=redis_host,
    port=redis_port,
    password=redis_password,
    ...
)

redis_client.ping()  # ❌ Can't await at module level
```

**After:**
```python
redis_password = os.getenv("REDIS_PASSWORD", "")  # ✅ Empty default

redis_kwargs = {
    "host": redis_host,
    "port": redis_port,
    ...
}

if redis_password:  # ✅ Only add password if set
    redis_kwargs["password"] = redis_password

redis_client = redis.Redis(**redis_kwargs)
# ✅ Removed ping() - tested in lifespan function
```

#### Change 2: Lifespan function Redis initialization (Lines 56-92)
**Before:**
```python
redis_password = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}"
```

**After:**
```python
redis_password = os.getenv("REDIS_PASSWORD", "")  # ✅ Empty default

if redis_password:
    redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}"
else:
    redis_url = f"redis://{redis_host}:{redis_port}"  # ✅ No password in URL
```

### File: `asr-service-secret.yaml`

**Before:**
```yaml
data:
  REDIS_PASSWORD: cmVkaXNfc2VjdXJlX3Bhc3N3b3JkXzIwMjQ=  # Old password
```

**After:**
```yaml
data:
  # Redis Password (base64 encoded) - must match redis-secret
  REDIS_PASSWORD: cmVkaXNwYXNz  # redispass in base64 (matches Redis secret)
```

### File: `redis-configmap.yaml` (NEW)

Created Redis ConfigMap with:
- `redis.conf` - Redis configuration file
- `redis-entrypoint.sh` - Entrypoint script that injects password from `REDIS_PASSWORD` env var

### File: `redis-deployment.yaml` (UPDATED)

**Changes:**
- Updated command to use entrypoint script: `["/usr/local/etc/redis/redis-entrypoint.sh"]`
- Changed volume mount to mount entire config directory instead of just redis.conf
- Added security context to run as Redis user (999:999)
- Changed configMap from `optional: true` to `defaultMode: 0755` for script execution

## Verification

To verify the changes are correct:

```bash
cd /home/ubuntu/AI4inclusion/k8s-manifests-models/micro-services/services/asr-service

# Check password defaults to empty
grep -n 'redis_password = os.getenv("REDIS_PASSWORD"' main.py
# Should show: redis_password = os.getenv("REDIS_PASSWORD", "")

# Check password is conditional
grep -n "if redis_password:" main.py
# Should show 3 occurrences (lines 63, 85, 253)

# Verify no un-awaited ping() at module level
grep -n "redis_client.ping()" main.py | grep -v "await"
# Should only show lines with "await redis_client.ping()"
```

## Build and Deploy

See `BUILD_INSTRUCTIONS.md` for detailed step-by-step instructions, or run:

```bash
./build-and-deploy.sh
```

