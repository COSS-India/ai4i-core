# Testing Health Monitoring and Auto-Recovery

This guide explains how to test the health monitoring and auto-recovery features.

## Prerequisites

1. **Start the config service** with health monitoring enabled:
   ```bash
   # Set environment variables
   export SERVICE_HEALTH_CHECK_ENABLED=true
   export SERVICE_HEALTH_CHECK_INTERVAL=30
   export HEALTH_CHECK_TIMEOUT=3.0
   export HEALTH_CHECK_MAX_RETRIES=3
   export HEALTH_CHECK_ADDITIONAL_ENDPOINTS=/ready,/live
   
   # Start the service
   cd services/config-service
   uvicorn main:app --reload --port 8082
   ```

2. **Register some test services** to monitor:
   ```bash
   # Register a service
   curl -X POST http://localhost:8082/api/v1/registry/register \
     -H 'Content-Type: application/json' \
     -d '{
       "service_name": "test-service",
       "service_url": "http://localhost:8080",
       "health_check_url": "http://localhost:8080/health",
       "service_metadata": {}
     }'
   ```

## Test Scenarios

### 1. Test Manual Health Check (Basic)

Test the basic health check endpoint:

```bash
# Trigger manual health check
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health

# Expected response:
# {"status": "healthy"} or {"status": "unhealthy"}
```

### 2. Test Detailed Health Check

Test the detailed health check with aggregation:

```bash
# Trigger detailed health check
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health/detailed

# Expected response:
# {
#   "service_name": "test-service",
#   "overall_status": "healthy",
#   "total_instances": 1,
#   "healthy_instances": 1,
#   "unhealthy_instances": 0,
#   "check_results": [
#     {
#       "endpoint_url": "http://localhost:8080/health",
#       "is_healthy": true,
#       "response_time_ms": 12.5,
#       "status_code": 200,
#       "error_message": null,
#       "timestamp": "2024-01-01T12:00:00Z"
#     }
#   ],
#   "timestamp": "2024-01-01T12:00:00Z"
# }
```

### 3. Test Automatic Periodic Health Checks

Check the logs to verify automatic health checks are running:

```bash
# Watch the logs
tail -f logs/config-service.log

# Or if running in terminal:
# You should see logs like:
# INFO: Starting periodic health check monitor (interval: 30s, additional endpoints: ['/ready', '/live'])
# INFO: Health check for test-service: healthy (1/1 healthy)
# DEBUG: Completed health check cycle for 1 services
```

**Verify in database:**
```bash
# Check service status in database
psql -h localhost -U dhruva_user -d config_db -c \
  "SELECT service_name, status, last_health_check FROM service_registry;"

# You should see:
#  service_name  | status  |      last_health_check
# ---------------+---------+------------------------
#  test-service  | healthy | 2024-01-01 12:00:00+00
```

### 4. Test Retry Logic with Exponential Backoff

To test retry logic, temporarily make a service unhealthy:

```bash
# 1. Start a mock service that will fail health checks
# Create a simple test server that returns 500 errors
python3 -m http.server 8080 --bind localhost

# 2. Register the service
curl -X POST http://localhost:8082/api/v1/registry/register \
  -H 'Content-Type: application/json' \
  -d '{
    "service_name": "failing-service",
    "service_url": "http://localhost:8080",
    "health_check_url": "http://localhost:8080/health"
  }'

# 3. Trigger health check and watch logs
curl -X POST http://localhost:8082/api/v1/registry/services/failing-service/health/detailed

# Expected behavior:
# - First attempt fails immediately
# - Retry after 1 second (initial delay)
# - Retry after 2 seconds (exponential backoff)
# - Retry after 4 seconds (exponential backoff)
# - Final result: unhealthy after max retries
```

### 5. Test Multi-Endpoint Aggregation

Test checking multiple endpoints:

```bash
# Register a service with multiple health endpoints
curl -X POST http://localhost:8082/api/v1/registry/register \
  -H 'Content-Type: application/json' \
  -d '{
    "service_name": "multi-endpoint-service",
    "service_url": "http://localhost:8080",
    "health_check_url": "http://localhost:8080/health"
  }'

# Trigger health check with additional endpoints
# The system will check:
# - /health (primary)
# - /ready (additional)
# - /live (additional)

curl -X POST http://localhost:8082/api/v1/registry/services/multi-endpoint-service/health/detailed

# Expected response includes checks for all endpoints:
# {
#   "check_results": [
#     {"endpoint_url": "http://localhost:8080/health", "is_healthy": true, ...},
#     {"endpoint_url": "http://localhost:8080/ready", "is_healthy": true, ...},
#     {"endpoint_url": "http://localhost:8080/live", "is_healthy": true, ...}
#   ]
# }
```

### 6. Test Service Recovery

Test automatic recovery when a service becomes healthy again:

```bash
# 1. Make service unhealthy (stop it)
# Stop the test service

# 2. Wait for automatic health check (or trigger manually)
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health

# Status should be: unhealthy

# 3. Start the service again
# Start your test service

# 4. Wait for next automatic check or trigger manually
curl -X POST http://localhost:8082/api/v1/registry/services/test-service/health

# Status should recover to: healthy
```

### 7. Test Multiple Service Instances

Test health monitoring with multiple instances:

```bash
# Register multiple instances of the same service
curl -X POST http://localhost:8082/api/v1/registry/register \
  -H 'Content-Type: application/json' \
  -d '{
    "service_name": "multi-instance-service",
    "service_url": "http://localhost:8081",
    "health_check_url": "http://localhost:8081/health"
  }'

curl -X POST http://localhost:8082/api/v1/registry/register \
  -H 'Content-Type: application/json' \
  -d '{
    "service_name": "multi-instance-service",
    "service_url": "http://localhost:8082",
    "health_check_url": "http://localhost:8082/health"
  }'

# Check aggregated health
curl -X POST http://localhost:8082/api/v1/registry/services/multi-instance-service/health/detailed

# Expected: Shows health for all instances
# If at least one instance is healthy, overall_status = "healthy"
```

## Monitoring and Verification

### Check Service Status

```bash
# List all services and their status
curl http://localhost:8082/api/v1/registry/services

# Get specific service instances
curl http://localhost:8082/api/v1/registry/services/test-service
```

### Check Logs

```bash
# Look for periodic health check logs
grep "Health check for" logs/config-service.log

# Look for retry attempts
grep "retrying" logs/config-service.log

# Look for errors
grep "ERROR" logs/config-service.log
```

### Check Database

```sql
-- Check service registry status
SELECT 
    service_name,
    status,
    last_health_check,
    updated_at
FROM service_registry
ORDER BY last_health_check DESC;
```

## Configuration Testing

### Test Different Intervals

```bash
# Set shorter interval for testing
export SERVICE_HEALTH_CHECK_INTERVAL=10

# Restart service
# Health checks should run every 10 seconds instead of 30
```

### Test Retry Configuration

```bash
# Set more retries for testing
export HEALTH_CHECK_MAX_RETRIES=5
export HEALTH_CHECK_INITIAL_RETRY_DELAY=0.5

# Restart service
# Health checks will retry 5 times with 0.5s initial delay
```

### Disable Automatic Health Checks

```bash
# Disable automatic health checks
export SERVICE_HEALTH_CHECK_ENABLED=false

# Restart service
# Manual health checks still work, but no background task runs
```

## Integration Testing Script

Create a test script to automate testing:

```bash
#!/bin/bash
# test_health_monitoring.sh

CONFIG_SERVICE="http://localhost:8082"
TEST_SERVICE="http://localhost:8080"

echo "=== Testing Health Monitoring ==="

# 1. Register test service
echo "1. Registering test service..."
curl -X POST "$CONFIG_SERVICE/api/v1/registry/register" \
  -H 'Content-Type: application/json' \
  -d "{
    \"service_name\": \"test-service\",
    \"service_url\": \"$TEST_SERVICE\",
    \"health_check_url\": \"$TEST_SERVICE/health\"
  }"

# 2. Test basic health check
echo -e "\n2. Testing basic health check..."
curl -X POST "$CONFIG_SERVICE/api/v1/registry/services/test-service/health"

# 3. Test detailed health check
echo -e "\n3. Testing detailed health check..."
curl -X POST "$CONFIG_SERVICE/api/v1/registry/services/test-service/health/detailed"

# 4. Wait for automatic check
echo -e "\n4. Waiting for automatic health check (30s)..."
sleep 35

# 5. Check service status
echo -e "\n5. Checking service status..."
curl "$CONFIG_SERVICE/api/v1/registry/services/test-service"

echo -e "\n=== Testing Complete ==="
```

## Troubleshooting

### Health checks not running automatically

- Check `SERVICE_HEALTH_CHECK_ENABLED=true` is set
- Check logs for "Periodic health check task started"
- Verify no errors in startup logs

### Retry logic not working

- Check `HEALTH_CHECK_MAX_RETRIES` is set correctly
- Verify service is actually failing (check logs)
- Check timeout is not too short

### Multiple endpoints not being checked

- Verify `HEALTH_CHECK_ADDITIONAL_ENDPOINTS` is set
- Check service has multiple endpoints available
- Review detailed health check response

### Status not updating

- Check database connection
- Verify `update_service_status` is being called
- Check for errors in logs

