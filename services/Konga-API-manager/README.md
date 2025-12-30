# Kong API Gateway for AIV4-Core

This directory contains the Kong API Gateway configuration and implementation files for the AIV4-Core microservices architecture.

## Overview

Kong Gateway serves as the centralized entry point for all API requests, providing:

- ✅ **Intelligent Request Routing** - Language-aware routing to appropriate services
- ✅ **Load Balancing** - Distribute requests across service instances
- ✅ **Rate Limiting** - Protect services from overload
- ✅ **Authentication** - API key-based authentication
- ✅ **Request/Response Transformation** - Modify requests/responses as needed
- ✅ **API Versioning** - Support multiple API versions
- ✅ **Health Checks** - Automatic service health monitoring

## Files

- `kong.yml` - Main Kong declarative configuration (DB-less mode)
- `kong-config.yaml` - Kubernetes configuration (legacy)
- `kong-config-simple.yaml` - Simplified configuration
- `kong-deployment.yaml` - Kubernetes deployment manifest
- `kong-ingress.yaml` - Kubernetes ingress configuration
- `kong-namespace.yaml` - Kubernetes namespace
- `IMPLEMENTATION_PROMPT.md` - Complete implementation guide

## Quick Start

### 1. Add Kong to docker-compose.yml

Add the following to the root `docker-compose.yml` (after the kafka service and before the microservices section):

```yaml
kong:
  image: kong:3.4
  container_name: ai4v-kong-gateway
  ports:
    - "8000:8000"      # Proxy port (entry point)
    - "8443:8443"      # SSL proxy port
    - "8001:8001"      # Admin API
    - "8444:8444"      # Admin API SSL
  environment:
    KONG_DATABASE: "off"  # Use DB-less mode
    KONG_DECLARATIVE_CONFIG: /kong/kong.yml
    KONG_PROXY_ACCESS_LOG: /dev/stdout
    KONG_ADMIN_ACCESS_LOG: /dev/stdout
    KONG_PROXY_ERROR_LOG: /dev/stderr
    KONG_ADMIN_ERROR_LOG: /dev/stderr
    KONG_ADMIN_LISTEN: 0.0.0.0:8001
    KONG_ADMIN_GUI_URL: http://localhost:8002
    REDIS_PASSWORD: ${REDIS_PASSWORD}
  volumes:
    - ./services/Kong-API-manager/kong.yml:/kong/kong.yml:ro
  networks:
    - microservices-network
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "kong", "health"]
    interval: 10s
    timeout: 10s
    retries: 5
    start_period: 30s
  restart: unless-stopped

# Optional: Kong Manager (Konga Web UI)
kong-manager:
  image: pantsel/konga:latest
  container_name: ai4v-kong-manager
  ports:
    - "8002:1337"      # Konga runs on port 1337 internally
  environment:
    NODE_ENV: production
    DB_ADAPTER: postgres
    DB_HOST: postgres
    DB_PORT: 5432
    DB_USER: ${POSTGRES_USER}
    DB_PASSWORD: ${POSTGRES_PASSWORD}
    DB_DATABASE: konga
    KONGA_HOOK_TIMEOUT: 120000
    TOKEN_SECRET: ${KONG_MANAGER_TOKEN_SECRET}
  depends_on:
    kong:
      condition: service_healthy
    postgres:
      condition: service_healthy
  networks:
    - microservices-network
  restart: unless-stopped
```

**Note:** Konga (Kong Manager) requires a PostgreSQL database. Ensure the `konga` database is created (see `infrastructure/postgres/init-databases.sql`).

### 2. Set Environment Variables

Add to `env.template` and `.env` file:

```bash
# Kong Gateway Configuration
KONG_DATABASE=off
KONG_DECLARATIVE_CONFIG=/kong/kong.yml

# Kong API Keys for Consumers
AI4VOICE_API_KEY=ai4voice-secure-key-2024-change-in-production
ASR_API_KEY=asr-secure-key-2024-change-in-production
TTS_API_KEY=tts-secure-key-2024-change-in-production
NMT_API_KEY=nmt-secure-key-2024-change-in-production
PIPELINE_API_KEY=pipeline-secure-key-2024-change-in-production
DEVELOPER_API_KEY=developer-secure-key-2024-change-in-production

# Kong Manager (Konga) Configuration
KONG_MANAGER_TOKEN_SECRET=konga-token-secret-2024-change-in-production

# Kong Service URL
KONG_GATEWAY_URL=http://kong:8000
```

**Important:** 
- The API keys in `env.template` are placeholder values. 
- For production, generate cryptographically secure random keys using `openssl rand -base64 32` or similar.
- The `.env` file (typically gitignored) should contain actual secrets, while `env.template` contains placeholder values for documentation.

### 3. Start Services

```bash
# Start Kong Gateway and Kong Manager
docker-compose up -d kong kong-manager

# Verify Kong is running
curl http://localhost:8001/

# Check Kong health
curl http://localhost:8001/status
```

**First-time Konga Setup:**

1. Access Konga at `http://localhost:8002`
2. Create an admin user account (username, email, password)
3. Connect to Kong Admin API:
   - **Name:** Kong Gateway
   - **Kong Admin URL:** `http://kong:8001`
   - **Kong API Key:** (leave empty for DB-less mode)
4. Save the connection and verify services/routes are visible in the dashboard

### 4. Test Routes

```bash
# Test ASR service through Kong (requires API key)
export ASR_API_KEY="asr-secure-key-2024-change-in-production"
curl -X POST http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: ${ASR_API_KEY}" \
  -H "Content-Type: application/json"

# Test TTS service with different consumer API key
export TTS_API_KEY="tts-secure-key-2024-change-in-production"
curl -X POST http://localhost:8000/api/v1/tts/health \
  -H "X-API-Key: ${TTS_API_KEY}"

# Test NMT service
export NMT_API_KEY="nmt-secure-key-2024-change-in-production"
curl -X POST http://localhost:8000/api/v1/nmt/health \
  -H "X-API-Key: ${NMT_API_KEY}"

# Test Pipeline service
export PIPELINE_API_KEY="pipeline-secure-key-2024-change-in-production"
curl -X POST http://localhost:8000/api/v1/pipeline/health \
  -H "X-API-Key: ${PIPELINE_API_KEY}"

# Test Auth service (no API key required - public endpoint)
curl http://localhost:8000/api/v1/auth/health
```

**Troubleshooting:**

- **401 Unauthorized:** Verify API key is correct and matches the consumer in `kong.yml`
- **429 Rate Limited:** Rate limit exceeded, wait before retrying or check rate limit settings
- **404 Not Found:** Verify service is running and route path matches (e.g., `/api/v1/asr/health`)

## API Endpoints

All API requests should now go through Kong Gateway at port `8000`:

| Service | Route | Auth Required | Rate Limit |
|---------|-------|---------------|------------|
| Auth | `/api/v1/auth/*` | No | 200/min |
| Config | `/api/v1/config/*` | Yes | 200/min |
| Metrics | `/api/v1/metrics/*` | Yes | 300/min |
| Telemetry | `/api/v1/telemetry/*` | Yes | 500/min |
| Alerting | `/api/v1/alerting/*` | Yes | 200/min |
| Dashboard | `/api/v1/dashboard/*` | Yes | 100/min |
| ASR | `/api/v1/asr/*` | Yes | 100/min |
| TTS | `/api/v1/tts/*` | Yes | 100/min |
| NMT | `/api/v1/nmt/*` | Yes | 150/min |
| Pipeline | `/api/v1/pipeline/*` | Yes | 50/min |

## Authentication

### API Key Authentication

All AI services require an API key. Pass the key in one of these ways:

**Header:**
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/v1/asr/health
```

**Query Parameter:**
```bash
curl http://localhost:8000/api/v1/asr/health?apikey=your-api-key
```

**Authorization Header:**
```bash
curl -H "Authorization: Bearer your-api-key" http://localhost:8000/api/v1/asr/health
```

### Getting API Keys

API keys are configured in `kong.yml` under the `consumers` section. To create new consumers and keys:

```bash
# Via Kong Admin API
curl -X POST http://localhost:8001/consumers \
  -d "username=new-client"

curl -X POST http://localhost:8001/consumers/new-client/key-auth \
  -d "key=new-api-key"
```

## Rate Limiting

Rate limits are configured per service and per consumer. When a limit is exceeded, you'll receive:

```json
{
  "message": "API rate limit exceeded"
}
```

With HTTP status `429 Too Many Requests`.

Rate limit headers are included in responses:
- `X-RateLimit-Limit-*` - The limit
- `X-RateLimit-Remaining-*` - Remaining requests
- `X-RateLimit-Reset-*` - Reset time

## Load Balancing

Kong automatically load balances requests across service instances defined in upstreams. Unhealthy instances are automatically removed from the pool based on health checks.

## Health Checks

Health checks run automatically for all services:
- **Interval**: 10 seconds
- **Healthy threshold**: 2 consecutive successes
- **Unhealthy threshold**: 3 consecutive failures
- **Timeout**: 5 seconds

Check upstream health:
```bash
curl http://localhost:8001/upstreams/asr-service-upstream/health
```

## Monitoring

### Prometheus Metrics

Kong exposes Prometheus metrics at:
```
http://localhost:8001/metrics
```

Key metrics:
- `kong_http_requests_total` - Total requests
- `kong_latency_ms` - Request latency
- `kong_requests_per_consumer` - Requests per consumer
- `kong_upstream_target_health` - Upstream health status

### Kong Manager Dashboard (Konga)

Access the web UI at:
```
http://localhost:8002
```

Konga provides:
- **Service Management:** View and manage all configured services and routes
- **Consumer Management:** Create, update, and delete API consumers
- **API Key Management:** Generate and manage API keys for consumers
- **Plugin Configuration:** Configure rate limiting, CORS, and other plugins
- **Dashboard Analytics:** View request metrics, latency, and error rates
- **Health Monitoring:** Monitor upstream service health status

**Managing Consumers and API Keys:**

1. Login to Konga at `http://localhost:8002`
2. Navigate to **Consumers** section
3. View existing consumers (ai4voice-client, asr-client, tts-client, etc.)
4. Create new consumers or update existing ones
5. Generate new API keys or view existing keys for each consumer
6. Test API keys directly from the Konga UI

## Custom Plugins

### Language Router Plugin

For intelligent language-based routing, implement a custom Kong plugin. See `IMPLEMENTATION_PROMPT.md` for details.

The plugin should:
1. Extract language from request body/headers/query params
2. Route to appropriate service/model based on language
3. Fall back to default service if detection fails

## Troubleshooting

### Kong not starting

1. Check Kong logs:
```bash
docker logs ai4v-kong-gateway
```

2. Verify `kong.yml` syntax:
```bash
docker exec ai4v-kong-gateway kong config parse /tmp/kong-substituted.yml
```

3. Check Kong health:
```bash
curl http://localhost:8001/status
```

### Routes not working

1. List all routes:
```bash
curl http://localhost:8001/routes
```

2. Check service configuration:
```bash
curl http://localhost:8001/services
```

3. Test route matching:
```bash
curl -X POST http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: test-key" \
  -v
```

### Authentication failing

1. Verify consumer exists:
```bash
curl http://localhost:8001/consumers
```

2. Check API key:
```bash
curl http://localhost:8001/consumers/{username}/key-auth
```

3. Verify plugin is enabled:
```bash
curl http://localhost:8001/services/{service-name}/plugins
```

## Migration from FastAPI Gateway

1. **Update Frontend Configuration:**
   - Update `NEXT_PUBLIC_API_URL` environment variable in `docker-compose.yml` (simple-ui-frontend service) from `http://api-gateway-service:8080` to `http://kong:8000`
   - Alternatively, update `frontend/simple-ui/src/config/constants.ts` API endpoints if using direct service URLs

2. **Update Service Configuration:**
   - Update any service-to-service communication that references `API_GATEWAY_URL` to use `KONG_GATEWAY_URL` instead
   - Ensure all services use the Kong Gateway endpoint at `http://kong:8000`

3. **Migrate API Keys:**
   - Existing API keys need to be migrated to Kong consumers
   - Create Kong consumers via Konga UI or Admin API
   - Assign API keys to consumers matching the existing authentication scheme

4. **Test All Endpoints:**
   - Test all API endpoints through Kong Gateway
   - Verify authentication, rate limiting, and request routing
   - Check health endpoints and service responses

5. **Deprecate FastAPI Gateway:**
   - Once verified, the FastAPI gateway service (`api-gateway-service`) can be deprecated or kept as a fallback
   - Update documentation to reflect Kong Gateway as the primary entry point

## Configuration Management

Kong uses declarative configuration in `kong.yml`. To update:

1. Edit `kong.yml`
2. Reload Kong configuration:
```bash
docker exec ai4v-kong-gateway kong reload
```

Or restart the container:
```bash
docker-compose restart kong
```

## Advanced Features

### SSL/TLS Termination

Add SSL configuration to Kong:
```yaml
environment:
  KONG_PROXY_LISTEN: 0.0.0.0:8000 ssl, 0.0.0.0:8443 ssl
  KONG_ADMIN_SSL_CERT: /path/to/cert.pem
  KONG_ADMIN_SSL_CERT_KEY: /path/to/key.pem
```

### Custom Plugins

Custom plugins should be placed in:
```
services/Kong-API-manager/plugins/
```

And mounted into Kong container:
```yaml
volumes:
  - ./services/Kong-API-manager/plugins:/usr/local/share/lua/5.1/kong/plugins
```

## Documentation

- [Kong Documentation](https://docs.konghq.com/)
- [Kong Plugin Development](https://docs.konghq.com/gateway/latest/plugin-development/)
- [Kong Admin API](https://docs.konghq.com/gateway/latest/admin-api/)
- [Implementation Guide](./IMPLEMENTATION_PROMPT.md)

## Support

For issues or questions:
1. Check the [Implementation Prompt](./IMPLEMENTATION_PROMPT.md)
2. Review Kong logs: `docker logs ai4v-kong-gateway`
3. Check Kong Admin API: `http://localhost:8001/`

