# Quick Test Guide - Health Monitoring

## Quick Start

### 1. Start the Config Service

```bash
cd services/config-service
export SERVICE_HEALTH_CHECK_ENABLED=true
export SERVICE_HEALTH_CHECK_INTERVAL=30
uvicorn main:app --reload --port 8082
```

**Look for these logs:**
```
INFO: Health monitor service initialized
INFO: Periodic health check task started
INFO: Starting periodic health check monitor (interval: 30s, additional endpoints: ['/ready', '/live'])
```

### 2. Register a Test Service

```bash
curl -X POST http://localhost:8082/api/v1/registry/register \
  -H 'Content-Type: application/json' \
  -d '{
    "service_name": "test-service",
    "service_url": "http://localhost:8080",
    "health_check_url": "http://localhost:8080/health"
  }'
```

### 3. Test Manual Health Check

```bash
# Basic health check
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health

# Expected: {"status": "healthy"} or {"status": "unhealthy"}
```

### 4. Test Detailed Health Check

```bash
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health/detailed | jq

# Expected: Detailed JSON with check results, response times, etc.
```

### 5. Verify Automatic Periodic Checks

**Wait 30 seconds** (or your configured interval), then check logs:

```bash
# Look for periodic check logs
grep "Health check for" logs/config-service.log

# Or watch logs in real-time
tail -f logs/config-service.log | grep "Health check"
```

**Expected logs:**
```
INFO: Health check for test-service: healthy (1/1 healthy)
DEBUG: Completed health check cycle for 1 services
```

### 6. Check Service Status in Database

```bash
# Using psql
psql -h localhost -U dhruva_user -d config_db -c \
  "SELECT service_name, status, last_health_check FROM service_registry;"

# Or using curl to check status
curl http://localhost:8082/api/v1/registry/services/test-service | jq
```

## Verify Features

### ✅ Automatic Periodic Health Checks

**Check logs every 30 seconds:**
- Should see: `"Health check for {service_name}: {status} ({healthy}/{total} healthy)"`
- Database `last_health_check` should update

### ✅ Retry Logic with Exponential Backoff

**Make a service unhealthy:**
```bash
# Stop a test service or make it return 500
# Then trigger health check:
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health/detailed

# Check logs for retry messages:
grep "retrying" logs/config-service.log
```

**Expected:**
- First attempt fails
- Retry after 1s (initial delay)
- Retry after 2s (exponential backoff)
- Retry after 4s (exponential backoff)
- Final result after max retries

### ✅ Multi-Endpoint Aggregation

**Check detailed health check response:**
```bash
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health/detailed | jq '.check_results'

# Should show multiple endpoints if HEALTH_CHECK_ADDITIONAL_ENDPOINTS is set
```

**Expected:**
- Primary endpoint: `/health`
- Additional endpoints: `/ready`, `/live` (if configured)
- All endpoints checked and aggregated

### ✅ Auto-Recovery

**Test recovery:**
1. Make service unhealthy (stop it)
2. Wait for automatic check or trigger manually
3. Status should be: `unhealthy`
4. Start service again
5. Wait for next automatic check
6. Status should recover to: `healthy`

## Run Automated Test Script

```bash
# Install httpx if not already installed
pip install httpx

# Run the test script
python3 services/config-service/test_health_monitoring.py
```

## Common Issues

### Health checks not running automatically

**Check:**
- `SERVICE_HEALTH_CHECK_ENABLED=true` is set
- Logs show: `"Periodic health check task started"`
- No errors in startup logs

### Retry logic not working

**Check:**
- `HEALTH_CHECK_MAX_RETRIES` is set (default: 3)
- Service is actually failing (check logs)
- Timeout is not too short

### Status not updating

**Check:**
- Database connection is working
- Service is registered correctly
- No errors in logs

## Monitoring Commands

```bash
# Watch logs for health checks
tail -f logs/config-service.log | grep -E "(Health check|retrying|health check)"

# Check all service statuses
curl http://localhost:8082/api/v1/registry/services | jq

# Check specific service details
curl http://localhost:8082/api/v1/registry/services/test-service | jq

# Trigger health check manually
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health

# Get detailed health check results
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health/detailed | jq
```

## Expected Behavior

1. **On Startup:**
   - Health monitor service initializes
   - Periodic health check task starts
   - Logs show: `"Starting periodic health check monitor"`

2. **Every 30 seconds (or configured interval):**
   - All registered services are checked
   - Logs show: `"Health check for {service}: {status}"`
   - Database `last_health_check` is updated

3. **On Health Check Failure:**
   - Retries with exponential backoff (1s → 2s → 4s)
   - Logs show: `"retrying in {delay}s"`
   - Final status updated after max retries

4. **On Service Recovery:**
   - Next health check detects recovery
   - Status changes from `unhealthy` to `healthy`
   - Logs show updated status

