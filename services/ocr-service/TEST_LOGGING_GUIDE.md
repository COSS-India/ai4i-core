# Testing Guide: Structured Logging Integration

This guide helps you verify that structured JSON logging with trace correlation is working correctly in OCR service.

## Prerequisites

1. OCR service is running (via docker-compose)
2. You have access to terminal/command line

---

## Test 1: Verify Service is Running

```bash
# Check if OCR service container is running
docker compose ps ocr-service

# Check service health
curl http://localhost:8099/health
```

**Expected Result:**
- Service returns `{"service": "ocr-service", "status": "ok", ...}`

---

## Test 2: Verify JSON Log Format

```bash
# Send a simple request
curl http://localhost:8099/health

# Check logs - should see JSON format
docker compose logs ocr-service --tail 5 | grep -E '^\{"timestamp'
```

**Expected Result:**
- Logs should be in JSON format starting with `{"timestamp": ...}`
- Should include fields: `timestamp`, `level`, `service`, `message`, `trace_id`

**Example Output:**
```json
{"timestamp": "2025-12-15T14:27:12.983750+00:00", "level": "INFO", "service": "middleware.request_logging", "message": "GET /health - 200 - 0.003s", "trace_id": "...", ...}
```

---

## Test 3: Test Correlation ID Extraction

```bash
# Send request WITH correlation ID
curl -H "X-Correlation-ID: test-123-abc" http://localhost:8099/health

# Check logs for the correlation ID
docker compose logs ocr-service --tail 10 | grep "test-123-abc"
```

**Expected Result:**
- Log should contain `"trace_id": "test-123-abc"`
- Response header should include `X-Correlation-ID: test-123-abc`

**Verify Response Header:**
```bash
curl -v -H "X-Correlation-ID: test-123-abc" http://localhost:8099/health 2>&1 | grep -i "x-correlation-id"
```

---

## Test 4: Test Auto-Generated Trace ID

```bash
# Send request WITHOUT correlation ID
curl http://localhost:8099/health

# Check logs - should have auto-generated UUID
docker compose logs ocr-service --tail 5 | grep -E '"trace_id"' | tail -1
```

**Expected Result:**
- Log should contain `"trace_id": "<uuid>"` (auto-generated UUID format)
- UUID format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

---

## Test 5: Verify Request Context in Logs

```bash
# Send a request
curl http://localhost:8099/health

# Extract and pretty-print the last log entry
docker compose logs ocr-service --tail 1 | grep -E '^\{"timestamp' | python3 -m json.tool
```

**Expected Result:**
- Log should include `context` field with:
  - `method`: "GET"
  - `path`: "/health"
  - `status_code`: 200
  - `duration_ms`: <number>
  - `client_ip`: <ip address>
  - `user_agent`: <user agent string>

---

## Test 6: Test Different Endpoints

```bash
# Test root endpoint
curl http://localhost:8099/

# Test health endpoint
curl http://localhost:8099/health

# Check logs for both
docker compose logs ocr-service --tail 10 | grep -E '^\{"timestamp'
```

**Expected Result:**
- Both requests should generate JSON logs
- Each log should have unique `trace_id`
- Logs should show different `path` values

---

## Test 7: Test Error Logging

```bash
# Send request to non-existent endpoint (should return 404)
curl http://localhost:8099/nonexistent

# Check logs for error
docker compose logs ocr-service --tail 5 | grep -E '"level":\s*"(WARNING|ERROR)"'
```

**Expected Result:**
- Log should have `"level": "WARNING"` (for 404)
- Should include full context in JSON format

---

## Test 8: Verify Service Metadata

```bash
# Send any request
curl http://localhost:8099/health

# Extract service metadata from logs
docker compose logs ocr-service --tail 1 | grep -E '^\{"timestamp' | python3 -c "import sys, json; log=json.load(sys.stdin); print(f\"Service: {log.get('service')}\nVersion: {log.get('service_version')}\nEnvironment: {log.get('environment')}\nHostname: {log.get('hostname')}\")"
```

**Expected Result:**
- `service`: "ocr-service" or "middleware.request_logging"
- `service_version`: "1.0.0"
- `environment`: "development" (or your env value)
- `hostname`: Container hostname

---

## Test 9: Test Multiple Requests with Same Correlation ID

```bash
# Send 3 requests with same correlation ID
for i in {1..3}; do
  curl -H "X-Correlation-ID: multi-test-456" http://localhost:8099/health
  sleep 1
done

# Check all logs have same trace_id
docker compose logs ocr-service --tail 10 | grep "multi-test-456" | wc -l
```

**Expected Result:**
- Should find 3 log entries (or more if other requests)
- All should have `"trace_id": "multi-test-456"`

---

## Test 10: Verify Kafka Fallback (if Kafka not available)

```bash
# Check if Kafka is running
docker compose ps kafka

# If Kafka is not running, logs should still work (fallback to stdout)
curl http://localhost:8099/health

# Check logs - should still be JSON format
docker compose logs ocr-service --tail 3 | grep -E '^\{"timestamp'
```

**Expected Result:**
- Logs should still be in JSON format
- Should work even if Kafka is unavailable
- No errors in logs about Kafka connection

---

## Quick Test Script

Save this as `test_ocr_logging.sh`:

```bash
#!/bin/bash

echo "🧪 Testing OCR Service Structured Logging"
echo "=========================================="
echo ""

echo "1. Testing service health..."
curl -s http://localhost:8099/health > /dev/null && echo "✅ Service is running" || echo "❌ Service not responding"

echo ""
echo "2. Testing JSON log format..."
sleep 1
curl -s http://localhost:8099/health > /dev/null
LOG_COUNT=$(docker compose logs ocr-service --tail 5 | grep -c '^{"timestamp')
if [ $LOG_COUNT -gt 0 ]; then
    echo "✅ JSON logs detected"
else
    echo "❌ No JSON logs found"
fi

echo ""
echo "3. Testing correlation ID extraction..."
curl -s -H "X-Correlation-ID: test-corr-123" http://localhost:8099/health > /dev/null
sleep 1
CORR_FOUND=$(docker compose logs ocr-service --tail 10 | grep -c "test-corr-123")
if [ $CORR_FOUND -gt 0 ]; then
    echo "✅ Correlation ID extracted correctly"
else
    echo "❌ Correlation ID not found in logs"
fi

echo ""
echo "4. Testing auto-generated trace ID..."
curl -s http://localhost:8099/health > /dev/null
sleep 1
UUID_FOUND=$(docker compose logs ocr-service --tail 5 | grep -oE '"trace_id":\s*"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"' | wc -l)
if [ $UUID_FOUND -gt 0 ]; then
    echo "✅ Auto-generated trace ID detected"
else
    echo "❌ No UUID trace ID found"
fi

echo ""
echo "5. Sample log entry:"
docker compose logs ocr-service --tail 1 | grep -E '^{"timestamp' | python3 -m json.tool 2>/dev/null | head -15

echo ""
echo "✅ Testing complete!"
```

Make it executable and run:
```bash
chmod +x test_ocr_logging.sh
./test_ocr_logging.sh
```

---

## Manual Verification Checklist

- [ ] Service responds to health check
- [ ] Logs are in JSON format (not plain text)
- [ ] Logs include `trace_id` field
- [ ] Correlation ID from header appears in logs
- [ ] Auto-generated UUID when no correlation ID provided
- [ ] Logs include `context` field with request details
- [ ] Logs include service metadata (service, version, environment, hostname)
- [ ] Different log levels work (INFO, WARNING, ERROR)
- [ ] Multiple requests generate different trace IDs
- [ ] Same correlation ID appears in multiple logs

---

## Troubleshooting

### If logs are still in plain text format:
```bash
# Rebuild the container
docker compose build ocr-service
docker compose restart ocr-service
```

### If correlation ID not working:
```bash
# Check if middleware is added in main.py
grep -A 2 "CorrelationMiddleware" services/ocr-service/main.py
```

### If JSON format is broken:
```bash
# Check if logging library is installed
docker compose exec ocr-service python3 -c "from ai4icore_logging import get_logger; print('OK')"
```

---

## Expected Log Format

Every log should look like this:

```json
{
  "timestamp": "2025-12-15T14:27:12.983750+00:00",
  "level": "INFO",
  "service": "middleware.request_logging",
  "message": "GET /health - 200 - 0.003s",
  "trace_id": "abc-123-def",
  "service_version": "1.0.0",
  "environment": "development",
  "hostname": "fa08043d8fc0",
  "logger": "middleware.request_logging",
  "context": {
    "method": "GET",
    "path": "/health",
    "status_code": 200,
    "duration_ms": 3.16,
    "client_ip": "127.0.0.1",
    "user_agent": "curl/7.81.0"
  }
}
```



