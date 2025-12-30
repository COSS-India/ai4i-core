# Kong Manager Validation Guide for AIV4-Core

This document provides comprehensive steps to validate all Kong Gateway capabilities implemented in AIV4-Core.

## Prerequisites

1. All services are running:
   ```bash
   docker-compose ps
   ```

2. Kong and Kong Manager are healthy:
   ```bash
   curl http://localhost:8001/status
   ```

3. Environment variables are set (check `.env` file):
   - `AI4VOICE_API_KEY`
   - `ASR_API_KEY`
   - `TTS_API_KEY`
   - `NMT_API_KEY`
   - `PIPELINE_API_KEY`
   - `DEVELOPER_API_KEY`
   - `REDIS_PASSWORD`

---

## Phase 1: Basic Connectivity & Health Checks

### 1.1 Kong Gateway Health

**Validate:** Kong is running and healthy

```bash
# Check Kong status
curl http://localhost:8001/status | jq

# Expected: Status 200 with healthy response
```

**Success Criteria:**
- HTTP 200 response
- `database.reachable: true`
- No error messages

---

### 1.2 Kong Manager (Konga) Access

**Validate:** Kong Manager UI is accessible

```bash
# Check Konga is running
curl http://localhost:8002

# Or open in browser: http://localhost:8002
```

**Success Criteria:**
- Web UI loads successfully
- Can login/create admin account
- Can connect to Kong Admin API

**Manual Steps:**
1. Open `http://localhost:8002`
2. Create admin account (first-time setup)
3. Add Kong connection:
   - Name: `Kong Gateway`
   - Kong Admin URL: `http://kong:8001`
   - Kong API Key: (leave empty for DB-less mode)
4. Verify connection shows green status

---

### 1.3 Configuration Validation

**Validate:** Kong configuration is valid

```bash
# Check Kong config syntax
docker exec ai4v-kong-gateway kong config parse /tmp/kong-substituted.yml

# Verify configuration loaded
curl http://localhost:8001/config | jq
```

**Success Criteria:**
- Config check passes without errors
- Configuration shows all services, routes, and plugins

---

## Phase 2: Service Discovery & Routing

### 2.1 All Services Registered

**Validate:** All 10 services are registered in Kong

```bash
# List all services
curl http://localhost:8001/services | jq '.data[] | .name'

# Expected services:
# - auth-service
# - config-service
# - metrics-service
# - telemetry-service
# - alerting-service
# - dashboard-service
# - asr-service
# - tts-service
# - nmt-service
# - pipeline-service
```

**Success Criteria:**
- All 10 services listed
- Each service has correct URL (upstream reference)

---

### 2.2 All Routes Configured

**Validate:** All routes are properly configured

```bash
# List all routes
curl http://localhost:8001/routes | jq '.data[] | {name: .name, paths: .paths, service: .service.name}'

# Expected routes:
# - auth-route: /api/v1/auth
# - config-route: /api/v1/config
# - metrics-route: /api/v1/metrics
# - telemetry-route: /api/v1/telemetry
# - alerting-route: /api/v1/alerting
# - dashboard-route: /api/v1/dashboard
# - asr-route: /api/v1/asr
# - tts-route: /api/v1/tts
# - nmt-route: /api/v1/nmt
# - pipeline-route: /api/v1/pipeline
```

**Success Criteria:**
- All 10 routes listed
- Each route points to correct service
- Paths match expected patterns

---

### 2.3 Route Path Matching

**Validate:** Routes correctly match and forward requests

```bash
# Test public route (auth-service - no auth required)
curl -v http://localhost:8000/api/v1/auth/health

# Test protected route (should fail without API key)
curl -v http://localhost:8000/api/v1/asr/health

# Expected: 401 Unauthorized for protected routes without key
```

**Success Criteria:**
- Public routes return 200/404 (service response)
- Protected routes return 401 without API key

---

## Phase 3: Upstreams & Load Balancing

### 3.1 All Upstreams Created

**Validate:** All upstreams are configured

```bash
# List all upstreams
curl http://localhost:8001/upstreams | jq '.data[] | .name'

# Expected upstreams:
# - auth-service-upstream
# - config-service-upstream
# - metrics-service-upstream
# - telemetry-service-upstream
# - alerting-service-upstream
# - dashboard-service-upstream
# - asr-service-upstream (with round-robin algorithm)
# - tts-service-upstream (with round-robin algorithm)
# - nmt-service-upstream (with round-robin algorithm)
# - pipeline-service-upstream (with round-robin algorithm)
```

**Success Criteria:**
- All 10 upstreams listed
- AI services (ASR, TTS, NMT, Pipeline) have `algorithm: round-robin`

---

### 3.2 Targets Configured

**Validate:** All targets are registered to upstreams

```bash
# Check targets for each upstream
curl http://localhost:8001/upstreams/asr-service-upstream/targets | jq '.data[] | {target: .target, weight: .weight, upstream: .upstream.name}'

# Verify all services have targets
for service in auth-service config-service metrics-service telemetry-service alerting-service dashboard-service asr-service tts-service nmt-service pipeline-service; do
  upstream="${service}-upstream"
  echo "Checking $upstream:"
  curl -s http://localhost:8001/upstreams/$upstream/targets | jq '.data[] | .target'
done
```

**Success Criteria:**
- Each upstream has at least one target
- Targets point to correct service:port (e.g., `asr-service:8087`)
- Weights are set (typically 100)

---

### 3.3 Health Checks Active

**Validate:** Health checks are monitoring upstreams

```bash
# Check health for ASR service upstream
curl http://localhost:8001/upstreams/asr-service-upstream/health | jq

# Check health for all upstreams
curl http://localhost:8001/upstreams | jq -r '.data[].name' | while read upstream; do
  echo "Health check for $upstream:"
  curl -s http://localhost:8001/upstreams/$upstream/health | jq '.data[] | {target: .target, health: .health}'
done
```

**Success Criteria:**
- Health check endpoints respond
- Targets show health status (`HEALTHY`, `UNHEALTHY`, or `UNKNOWN`)
- Health check configuration shows:
  - Interval: 10 seconds
  - Healthy threshold: 2 successes
  - Unhealthy threshold: 3 failures

---

## Phase 4: Authentication & Consumers

### 4.1 All Consumers Created

**Validate:** All 6 consumers are registered

```bash
# List all consumers
curl http://localhost:8001/consumers | jq '.data[] | {username: .username, tags: .tags}'

# Expected consumers:
# - ai4voice-client
# - asr-client
# - tts-client
# - nmt-client
# - pipeline-client
# - developer-client
```

**Success Criteria:**
- All 6 consumers listed
- Tags are correctly assigned (e.g., `production`, `development`)

---

### 4.2 API Keys Configured

**Validate:** API keys are assigned to consumers

```bash
# Get API keys from environment
export ASR_API_KEY=$(grep ASR_API_KEY .env | cut -d '=' -f2)

# Check API key for asr-client
curl http://localhost:8001/consumers/asr-client/key-auth | jq '.data[] | {key: .key, consumer: .consumer.id}'

# Verify all consumers have keys
for consumer in ai4voice-client asr-client tts-client nmt-client pipeline-client developer-client; do
  echo "Checking $consumer:"
  curl -s http://localhost:8001/consumers/$consumer/key-auth | jq '.data[] | .key'
done
```

**Success Criteria:**
- Each consumer has at least one API key
- Keys match values from `.env` file
- Key tags are present (e.g., `asr-only`, `full-access`)

---

### 4.3 Key-Auth Plugin Active

**Validate:** key-auth plugin is enabled on protected services

```bash
# Check plugins for ASR service
curl http://localhost:8001/services/asr-service/plugins | jq '.data[] | select(.name=="key-auth") | {name: .name, config: .config}'

# Verify all protected services have key-auth plugin
for service in config-service metrics-service telemetry-service alerting-service dashboard-service asr-service tts-service nmt-service pipeline-service; do
  echo "Checking $service:"
  curl -s http://localhost:8001/services/$service/plugins | jq '.data[] | select(.name=="key-auth") | .name'
done
```

**Success Criteria:**
- All protected services have `key-auth` plugin enabled
- Plugin config includes:
  - `key_names: ["apikey", "X-API-Key"]`
  - `hide_credentials: true`

---

### 4.4 Authentication Flow

**Validate:** API keys authenticate correctly

```bash
# Get API keys
export ASR_API_KEY=$(grep ASR_API_KEY .env | cut -d '=' -f2)
export TTS_API_KEY=$(grep TTS_API_KEY .env | cut -d '=' -f2)

# Test with valid API key (should succeed)
curl -v http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: ${ASR_API_KEY}"

# Test with invalid API key (should fail)
curl -v http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: invalid-key-12345"

# Expected: 401 Unauthorized for invalid key
```

**Success Criteria:**
- Valid API key returns service response (200/404)
- Invalid API key returns 401 Unauthorized
- No API key returns 401 for protected endpoints

---

## Phase 5: Rate Limiting

### 5.1 Rate Limiting Plugins Configured

**Validate:** Rate limiting is enabled on all routes

```bash
# Check rate-limiting plugin for ASR route
curl http://localhost:8001/routes/asr-route/plugins | jq '.data[] | select(.name=="rate-limiting") | {name: .name, config: .config}'

# Verify all routes have rate-limiting with correct configs
for route in auth-route config-route metrics-route telemetry-route alerting-route dashboard-route asr-route tts-route nmt-route pipeline-route; do
  echo "Rate limit config for $route:"
  curl -s http://localhost:8001/routes/$route/plugins | \
    jq '.data[] | select(.name=="rate-limiting") | {minute: .config.minute, hour: .config.hour, policy: .config.policy, limit_by: .config.limit_by}'
done
```

**Success Criteria:**
- All routes have `rate-limiting` plugin configured
- Policy is `redis` (using Redis backend)
- Limits match expected values:
  - Auth: 200/min, 2000/hour
  - Config: 200/min, 2000/hour
  - Metrics: 300/min, 3000/hour
  - Telemetry: 500/min, 5000/hour
  - Alerting: 200/min, 2000/hour
  - Dashboard: 100/min, 1000/hour
  - ASR: 100/min, 1000/hour
  - TTS: 100/min, 1000/hour
  - NMT: 150/min, 1500/hour
  - Pipeline: 50/min, 500/hour

---

### 5.2 Redis Configuration

**Validate:** Rate limiting uses Redis backend

```bash
# Check Redis config in rate-limiting plugin (at route level)
curl http://localhost:8001/routes/asr-route/plugins | \
  jq '.data[] | select(.name=="rate-limiting") | {policy: .config.policy, redis_host: .config.redis_host, redis_port: .config.redis_port, redis_timeout: .config.redis_timeout, redis_ssl: .config.redis_ssl, redis_ssl_verify: .config.redis_ssl_verify}'

# Verify Redis connection settings:
# - policy: redis
# - redis_host: redis
# - redis_port: 6379
# - redis_password: (substituted from ${REDIS_PASSWORD})
# - redis_database: 1
# - redis_timeout: 2000
# - redis_ssl: false
# - redis_ssl_verify: false
```

**Success Criteria:**
- Redis config present in all rate-limiting plugins
- Redis host points to `redis` service
- Password is correctly configured
- All Redis settings consistent across services

---

### 5.3 Rate Limit Enforcement

**Validate:** Rate limits are enforced

```bash
# Get API key
export ASR_API_KEY=$(grep ASR_API_KEY .env | cut -d '=' -f2)

# Make requests up to rate limit
for i in {1..105}; do
  response=$(curl -s -w "%{http_code}" -o /dev/null \
    http://localhost:8000/api/v1/asr/health \
    -H "X-API-Key: ${ASR_API_KEY}")
  
  if [ "$response" == "429" ]; then
    echo "Rate limit hit at request $i"
    break
  fi
  
  # Check rate limit headers
  curl -s -I http://localhost:8000/api/v1/asr/health \
    -H "X-API-Key: ${ASR_API_KEY}" | \
    grep -i "rate-limit"
done

# Expected: 429 Too Many Requests after exceeding limit
# Headers: X-RateLimit-Limit-Minute, X-RateLimit-Remaining-Minute
```

**Success Criteria:**
- Rate limit headers present in responses
- 429 error returned after exceeding limit
- Different consumers have separate rate limits

---

## Phase 6: Request/Response Transformation

### 6.1 Request Transformer Plugin

**Validate:** Request headers are added/modified

```bash
# Check request-transformer plugin
curl http://localhost:8001/services/asr-service/plugins | \
  jq '.data[] | select(.name=="request-transformer") | .config'

# Make request and verify headers are added
curl -v http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: ${ASR_API_KEY}" \
  2>&1 | grep -i "x-correlation-id\|x-request-id\|x-gateway-timestamp"
```

**Success Criteria:**
- Services with request-transformer have:
  - `X-Correlation-ID` added
  - `X-Request-ID` added
  - `X-Gateway-Timestamp` (for AI services)
  - `X-Language-Detection-Source: Kong` (ASR service)

---

### 6.2 Response Transformer Plugin

**Validate:** Response headers are added

```bash
# Check response-transformer plugin
curl http://localhost:8001/services/asr-service/plugins | \
  jq '.data[] | select(.name=="response-transformer") | .config'

# Make request and check response headers
curl -I http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: ${ASR_API_KEY}" | \
  grep -i "x-served-by\|x-service\|x-response-time"
```

**Success Criteria:**
- Response includes:
  - `X-Served-By: Kong-Gateway`
  - `X-Service: <Service-Name>` (e.g., `ASR-Service`)
  - `X-Response-Time` (for AI services)

---

## Phase 7: CORS Configuration

### 7.1 CORS Plugin Active

**Validate:** CORS is configured for AI services

```bash
# Check CORS plugin for ASR service
curl http://localhost:8001/services/asr-service/plugins | \
  jq '.data[] | select(.name=="cors") | {name: .name, config: .config}'

# Verify CORS on all AI services
for service in auth-service asr-service tts-service nmt-service pipeline-service; do
  echo "CORS config for $service:"
  curl -s http://localhost:8001/services/$service/plugins | \
    jq '.data[] | select(.name=="cors") | {origins: .config.origins, methods: .config.methods, credentials: .config.credentials}'
done
```

**Success Criteria:**
- CORS plugin enabled on:
  - `auth-service`
  - `asr-service`
  - `tts-service`
  - `nmt-service`
  - `pipeline-service`
- Config includes:
  - `origins: ["*"]`
  - `methods: ["GET", "POST", "OPTIONS", ...]`
  - `credentials: true`

---

### 7.2 CORS Preflight Requests

**Validate:** OPTIONS requests are handled correctly

```bash
# Test CORS preflight request
curl -X OPTIONS http://localhost:8000/api/v1/asr/health \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -v | grep -i "access-control"
```

**Success Criteria:**
- OPTIONS request returns 200 OK
- Response includes:
  - `Access-Control-Allow-Origin: *`
  - `Access-Control-Allow-Methods: ...`
  - `Access-Control-Allow-Credentials: true`

---

## Phase 8: Global Plugins

### 8.1 Prometheus Plugin

**Validate:** Prometheus metrics are exposed

```bash
# Check Prometheus plugin
curl http://localhost:8001/plugins | \
  jq '.data[] | select(.name=="prometheus") | .config'

# Access metrics endpoint
curl http://localhost:8001/metrics | head -20

# Check for key metrics
curl http://localhost:8001/metrics | grep -E "kong_http_requests_total|kong_latency_ms|kong_upstream_target_health"
```

**Success Criteria:**
- Prometheus plugin enabled globally
- Metrics endpoint accessible at `/metrics`
- Key metrics present:
  - `kong_http_requests_total`
  - `kong_latency_ms`
  - `kong_requests_per_consumer`
  - `kong_upstream_target_health`

---

### 8.2 Correlation ID Plugin

**Validate:** Correlation IDs are tracked

```bash
# Check correlation-id plugin
curl http://localhost:8001/plugins | \
  jq '.data[] | select(.name=="correlation-id") | .config'

# Make request and verify correlation ID
correlation_id=$(curl -s http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: ${ASR_API_KEY}" \
  -I | grep -i "x-correlation-id" | cut -d' ' -f2 | tr -d '\r')

echo "Correlation ID: $correlation_id"
```

**Success Criteria:**
- Correlation-ID plugin enabled globally
- Header name: `X-Correlation-ID`
- `echo_downstream: true`

---

### 8.3 Request ID Plugin

**Validate:** Request IDs are generated

```bash
# Check request-id plugin
curl http://localhost:8001/plugins | \
  jq '.data[] | select(.name=="request-id") | .config'

# Make request and verify request ID
request_id=$(curl -s http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: ${ASR_API_KEY}" \
  -I | grep -i "x-request-id" | cut -d' ' -f2 | tr -d '\r')

echo "Request ID: $request_id"
```

**Success Criteria:**
- Request-ID plugin enabled globally
- Header name: `X-Request-ID`
- Unique ID generated per request
- `echo_downstream: true`

---

## Phase 9: End-to-End Service Testing

### 9.1 Auth Service (Public)

**Validate:** Public endpoint works without authentication

```bash
# Test auth service (no API key required)
curl -v http://localhost:8000/api/v1/auth/health

# Expected: 200 OK or service response (not 401)
```

**Success Criteria:**
- Returns valid response (200/404/500)
- No 401 Unauthorized error
- Rate limiting still applies (by IP)

---

### 9.2 AI Services with Authentication

**Validate:** Protected services require API keys

```bash
# Get API keys
export ASR_API_KEY=$(grep ASR_API_KEY .env | cut -d '=' -f2)
export TTS_API_KEY=$(grep TTS_API_KEY .env | cut -d '=' -f2)
export NMT_API_KEY=$(grep NMT_API_KEY .env | cut -d '=' -f2)
export PIPELINE_API_KEY=$(grep PIPELINE_API_KEY .env | cut -d '=' -f2)

# Test ASR service
curl http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: ${ASR_API_KEY}"

# Test TTS service
curl http://localhost:8000/api/v1/tts/health \
  -H "X-API-Key: ${TTS_API_KEY}"

# Test NMT service
curl http://localhost:8000/api/v1/nmt/health \
  -H "X-API-Key: ${NMT_API_KEY}"

# Test Pipeline service
curl http://localhost:8000/api/v1/pipeline/health \
  -H "X-API-Key: ${PIPELINE_API_KEY}"
```

**Success Criteria:**
- All services accessible with correct API key
- Cross-service API keys are rejected (ASR key can't access TTS)
- Proper service responses returned

---

### 9.3 Config/Metrics/Telemetry Services

**Validate:** Core services work through Kong

```bash
# Get API keys
export AI4VOICE_API_KEY=$(grep AI4VOICE_API_KEY .env | cut -d '=' -f2)
export ASR_API_KEY=$(grep ASR_API_KEY .env | cut -d '=' -f2)

# Test config service
curl http://localhost:8000/api/v1/config/health \
  -H "X-API-Key: ${AI4VOICE_API_KEY}"

# Test metrics service
curl http://localhost:8000/api/v1/metrics/health \
  -H "X-API-Key: ${AI4VOICE_API_KEY}"

# Test telemetry service
curl http://localhost:8000/api/v1/telemetry/health \
  -H "X-API-Key: ${AI4VOICE_API_KEY}"
```

**Success Criteria:**
- Services respond correctly
- Authentication works
- Rate limiting applies

---

## Phase 10: Kong Manager (Konga) UI Validation

### 10.1 Dashboard Access

**Validate:** Konga dashboard displays all services

**Manual Steps:**
1. Open `http://localhost:8002`
2. Login to Konga
3. Navigate to **Dashboard**
4. Verify all services are visible:
   - 10 services listed
   - Service health indicators shown
   - Metrics displayed

**Success Criteria:**
- Dashboard loads successfully
- All services visible
- No errors in browser console

---

### 10.2 Service Management

**Validate:** Services can be viewed in Konga

**Manual Steps:**
1. Navigate to **Services** section
2. Verify all 10 services listed:
   - auth-service
   - config-service
   - metrics-service
   - telemetry-service
   - alerting-service
   - dashboard-service
   - asr-service
   - tts-service
   - nmt-service
   - pipeline-service
3. Click on each service to view details
4. Check routes are associated correctly

**Success Criteria:**
- All services visible
- Service details accessible
- Routes associated correctly

---

### 10.3 Consumer Management

**Validate:** Consumers and API keys visible

**Manual Steps:**
1. Navigate to **Consumers** section
2. Verify 6 consumers listed:
   - ai4voice-client
   - asr-client
   - tts-client
   - nmt-client
   - pipeline-client
   - developer-client
3. Click on each consumer
4. Verify API keys are visible
5. Test API key from UI

**Success Criteria:**
- All consumers listed
- API keys visible
- Key authentication test works

---

### 10.4 Plugin Configuration

**Validate:** Plugins visible and configurable

**Manual Steps:**
1. Navigate to **Plugins** section
2. View global plugins:
   - prometheus
   - correlation-id
   - request-id
3. View service-specific plugins:
   - key-auth (on protected services)
   - rate-limiting (on all services)
   - cors (on AI services)
   - request-transformer (on AI services)
   - response-transformer (on AI services)
4. Verify plugin configurations

**Success Criteria:**
- All plugins visible
- Configurations match `kong.yml`
- Plugins can be enabled/disabled (for testing)

---

### 10.5 Analytics & Monitoring

**Validate:** Metrics and analytics display

**Manual Steps:**
1. Navigate to **Analytics** or **Metrics** section
2. Check request metrics:
   - Total requests
   - Requests per service
   - Requests per consumer
   - Error rates
   - Latency metrics
3. View upstream health status
4. Check rate limit status

**Success Criteria:**
- Metrics display correctly
- Real-time updates work
- Historical data available (if applicable)

---

## Phase 11: Integration Testing

### 11.1 Full Request Flow

**Validate:** Complete request path works

```bash
# Get API key
export ASR_API_KEY=$(grep ASR_API_KEY .env | cut -d '=' -f2)

# Make full request and capture all headers
curl -v http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: ${ASR_API_KEY}" \
  2>&1 | tee /tmp/kong-response.txt

# Verify:
# 1. Request goes through Kong (check logs)
# 2. Headers added/transformed
# 3. Service responds
# 4. Response headers added
```

**Success Criteria:**
- Request successfully routed
- All transformers applied
- Service response received
- Response headers modified

---

### 11.2 Error Handling

**Validate:** Error scenarios handled correctly

```bash
# Test invalid route
curl -v http://localhost:8000/api/v1/nonexistent

# Test invalid API key
curl -v http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: invalid-key"

# Test rate limit exceeded
export ASR_API_KEY=$(grep ASR_API_KEY .env | cut -d '=' -f2)
for i in {1..105}; do
  response=$(curl -s -w "%{http_code}" -o /dev/null \
    http://localhost:8000/api/v1/asr/health \
    -H "X-API-Key: ${ASR_API_KEY}")
  if [ "$response" == "429" ]; then
    echo "Rate limit hit correctly"
    break
  fi
done
```

**Success Criteria:**
- Invalid routes return 404
- Invalid API key returns 401
- Rate limit returns 429
- Error messages are clear

---

## Phase 12: Performance & Reliability

### 12.1 Load Testing

**Validate:** Kong handles concurrent requests

```bash
# Install Apache Bench (if not available)
# brew install apache-bench (macOS)
# or use curl in parallel

# Test concurrent requests
seq 1 100 | xargs -P 10 -I {} curl -s \
  -H "X-API-Key: ${ASR_API_KEY}" \
  http://localhost:8000/api/v1/asr/health > /dev/null

# Monitor Kong metrics during load
watch -n 1 'curl -s http://localhost:8001/metrics | grep kong_http_requests_total'
```

**Success Criteria:**
- Kong handles concurrent requests
- No errors or timeouts
- Metrics reflect load correctly

---

### 12.2 Upstream Health Recovery

**Validate:** Health checks detect and recover failures

```bash
# Check initial health
curl http://localhost:8001/upstreams/asr-service-upstream/health | jq

# Stop service temporarily
docker-compose stop asr-service

# Wait for health check to detect (may take 30 seconds)
sleep 35

# Check health status
curl http://localhost:8001/upstreams/asr-service-upstream/health | jq

# Restart service
docker-compose start asr-service

# Wait for recovery
sleep 35

# Verify service recovered
curl http://localhost:8001/upstreams/asr-service-upstream/health | jq
```

**Success Criteria:**
- Health checks detect failures
- Unhealthy targets removed from pool
- Targets re-added when healthy
- Automatic recovery works

---

## Quick Validation Script

Create a comprehensive validation script:

```bash
#!/bin/bash
# validate-kong.sh

echo "=== Kong Gateway Validation ==="

# Phase 1: Basic Health
echo "1. Checking Kong health..."
curl -s http://localhost:8001/status | jq '.database.reachable' || echo "FAIL: Kong not healthy"

# Phase 2: Services
echo "2. Checking services..."
service_count=$(curl -s http://localhost:8001/services | jq '.data | length')
echo "Services found: $service_count (expected: 10)"
[ "$service_count" -eq 10 ] && echo "PASS" || echo "FAIL"

# Phase 3: Routes
echo "3. Checking routes..."
route_count=$(curl -s http://localhost:8001/routes | jq '.data | length')
echo "Routes found: $route_count (expected: 10)"
[ "$route_count" -eq 10 ] && echo "PASS" || echo "FAIL"

# Phase 4: Consumers
echo "4. Checking consumers..."
consumer_count=$(curl -s http://localhost:8001/consumers | jq '.data | length')
echo "Consumers found: $consumer_count (expected: 6)"
[ "$consumer_count" -eq 6 ] && echo "PASS" || echo "FAIL"

# Phase 5: Authentication
echo "5. Testing authentication..."
export ASR_API_KEY=$(grep ASR_API_KEY .env | cut -d '=' -f2)
response=$(curl -s -w "%{http_code}" -o /dev/null \
  http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: ${ASR_API_KEY}")
[ "$response" != "401" ] && echo "PASS" || echo "FAIL: Authentication not working"

echo "=== Validation Complete ==="
```

---

## Summary Checklist

Use this checklist to track validation progress:

- [ ] Phase 1: Basic Connectivity & Health Checks
- [ ] Phase 2: Service Discovery & Routing
- [ ] Phase 3: Upstreams & Load Balancing
- [ ] Phase 4: Authentication & Consumers
- [ ] Phase 5: Rate Limiting
- [ ] Phase 6: Request/Response Transformation
- [ ] Phase 7: CORS Configuration
- [ ] Phase 8: Global Plugins
- [ ] Phase 9: End-to-End Service Testing
- [ ] Phase 10: Kong Manager (Konga) UI Validation
- [ ] Phase 11: Integration Testing
- [ ] Phase 12: Performance & Reliability

---

## Troubleshooting

### Common Issues

1. **Kong not starting:**
   ```bash
   docker logs ai4v-kong-gateway
   docker exec ai4v-kong-gateway kong config parse /tmp/kong-substituted.yml
   ```

2. **Routes not working:**
   ```bash
   curl http://localhost:8001/routes
   docker exec ai4v-kong-gateway kong reload
   ```

3. **Authentication failing:**
   ```bash
   # Verify API keys in .env match kong.yml
   grep ASR_API_KEY .env
   curl http://localhost:8001/consumers/asr-client/key-auth
   ```

4. **Rate limiting not working:**
   ```bash
   # Check Redis connection
   docker exec ai4v-kong-gateway ping redis
   # Verify Redis password in environment
   docker exec ai4v-kong-gateway env | grep REDIS
   ```

---

## Next Steps

After validation:
1. Document any issues found
2. Update configuration if needed
3. Set up monitoring dashboards
4. Configure alerts for critical metrics
5. Implement custom plugins if required

---

**Last Updated:** Based on AIV4-Core Kong implementation
**Kong Version:** 3.4
**Configuration Mode:** DB-less (Declarative)

