# Kong Gateway Quick Reference Guide

Quick commands and configuration snippets for AIV4-Core Kong Gateway.

## Service URLs

| Service | Internal URL | Kong Route | Port |
|---------|-------------|------------|------|
| Auth | `http://auth-service:8081` | `/api/v1/auth` | 8081 |
| Config | `http://config-service:8082` | `/api/v1/config` | 8082 |
| Metrics | `http://metrics-service:8083` | `/api/v1/metrics` | 8083 |
| Telemetry | `http://telemetry-service:8084` | `/api/v1/telemetry` | 8084 |
| Alerting | `http://alerting-service:8085` | `/api/v1/alerting` | 8085 |
| Dashboard | `http://dashboard-service:8086` | `/api/v1/dashboard` | 8086 |
| ASR | `http://asr-service:8087` | `/api/v1/asr` | 8087 |
| TTS | `http://tts-service:8088` | `/api/v1/tts` | 8088 |
| NMT | `http://nmt-service:8089` | `/api/v1/nmt` | 8089 |
| Pipeline | `http://pipeline-service:8090` | `/api/v1/pipeline` | 8090 |

## Kong Endpoints

| Endpoint | Description | Port |
|----------|------------|------|
| `http://localhost:8000` | Proxy (API Gateway) | 8000 |
| `http://localhost:8001` | Admin API | 8001 |
| `http://localhost:8002` | Kong Manager UI | 8002 |
| `http://localhost:8443` | SSL Proxy | 8443 |
| `http://localhost:8444` | Admin API SSL | 8444 |

## Common Commands

### Health Checks

```bash
# Kong health
curl http://localhost:8001/status

# Service health
curl http://localhost:8001/upstreams/asr-service-upstream/health

# All upstreams
curl http://localhost:8001/upstreams
```

### Routes

```bash
# List all routes
curl http://localhost:8001/routes

# Get specific route
curl http://localhost:8001/routes/{route-name}

# Test route
curl -v http://localhost:8000/api/v1/asr/health
```

### Services

```bash
# List all services
curl http://localhost:8001/services

# Get service details
curl http://localhost:8001/services/asr-service

# List routes for service
curl http://localhost:8001/services/asr-service/routes
```

### Consumers (API Keys)

```bash
# List all consumers
curl http://localhost:8001/consumers

# Create consumer
curl -X POST http://localhost:8001/consumers \
  -d "username=new-client"

# Add API key to consumer
curl -X POST http://localhost:8001/consumers/{username}/key-auth \
  -d "key=your-api-key"

# List consumer's API keys
curl http://localhost:8001/consumers/{username}/key-auth
```

### Plugins

```bash
# List all plugins
curl http://localhost:8001/plugins

# Get plugins for service
curl http://localhost:8001/services/asr-service/plugins

# Get plugins for route
curl http://localhost:8001/routes/asr-route/plugins

# Enable plugin on service
curl -X POST http://localhost:8001/services/asr-service/plugins \
  -d "name=rate-limiting" \
  -d "config.minute=100"
```

### Rate Limiting

```bash
# Check rate limit status
curl -v http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: your-key" \
  | grep -i "rate-limit"
```

## Configuration

### Reload Configuration

```bash
# Reload (DB-less mode)
docker exec ai4v-kong-gateway kong reload

# Or restart
docker-compose restart kong
```

### Validate Configuration

```bash
# Check config syntax
docker exec ai4v-kong-gateway kong config parse /tmp/kong-substituted.yml
```

## Testing API Endpoints

### Public Endpoint (No Auth)

```bash
curl http://localhost:8000/api/v1/auth/health
```

### Protected Endpoint (Requires API Key)

```bash
# Using header
curl http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: your-api-key"

# Using query parameter
curl "http://localhost:8000/api/v1/asr/health?apikey=your-api-key"
```

### ASR Inference Request

```bash
curl -X POST http://localhost:8000/api/v1/asr/inference \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "audio": [{"audioContent": "base64-encoded-audio"}],
    "config": {
      "serviceId": "asr-model-id",
      "language": {"sourceLanguage": "hi"},
      "audioFormat": "wav",
      "samplingRate": 16000
    }
  }'
```

### TTS Inference Request

```bash
curl -X POST http://localhost:8000/api/v1/tts/inference \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"source": "Hello world"}],
    "config": {
      "serviceId": "tts-model-id",
      "language": {"sourceLanguage": "en"},
      "gender": "female",
      "audioFormat": "wav"
    }
  }'
```

### NMT Inference Request

```bash
curl -X POST http://localhost:8000/api/v1/nmt/inference \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"source": "Hello world"}],
    "config": {
      "serviceId": "nmt-model-id",
      "language": {
        "sourceLanguage": "en",
        "targetLanguage": "hi"
      }
    }
  }'
```

## Rate Limits

| Service | Limit per Minute | Limit per Hour |
|---------|------------------|----------------|
| Auth | 200 | 2000 |
| Config | 200 | 2000 |
| Metrics | 300 | 3000 |
| Telemetry | 500 | 5000 |
| Alerting | 200 | 2000 |
| Dashboard | 100 | 1000 |
| ASR | 100 | 1000 |
| TTS | 100 | 1000 |
| NMT | 150 | 1500 |
| Pipeline | 50 | 500 |

## Environment Variables

Required in `.env`:

```bash
# Kong
KONG_DATABASE=off
KONG_DECLARATIVE_CONFIG=/kong/kong.yml

# API Keys
AI4VOICE_API_KEY=your-key-here
ASR_API_KEY=your-key-here
TTS_API_KEY=your-key-here
NMT_API_KEY=your-key-here
PIPELINE_API_KEY=your-key-here
DEVELOPER_API_KEY=your-key-here

# Redis (for rate limiting)
REDIS_PASSWORD=your-redis-password
```

## Response Headers

Kong adds these headers to responses:

- `X-Correlation-ID` - Request correlation ID
- `X-Request-ID` - Unique request ID
- `X-Served-By` - Service that handled request
- `X-Gateway-Version` - Kong version
- `X-Response-Time` - Response time in milliseconds
- `X-RateLimit-Limit-*` - Rate limit information
- `X-RateLimit-Remaining-*` - Remaining requests
- `X-RateLimit-Reset-*` - Reset timestamp

## Troubleshooting

### Check Kong Logs

```bash
# All logs
docker logs ai4v-kong-gateway

# Follow logs
docker logs -f ai4v-kong-gateway

# Last 100 lines
docker logs --tail 100 ai4v-kong-gateway
```

### Verify Service Connectivity

```bash
# From Kong container, test service
docker exec ai4v-kong-gateway curl http://asr-service:8087/api/v1/asr/health
```

### Check Plugin Configuration

```bash
# List all plugins
curl http://localhost:8001/plugins | jq

# Check specific plugin
curl http://localhost:8001/plugins/{plugin-id} | jq
```

### Debug Route Matching

```bash
# Test route with verbose output
curl -v http://localhost:8000/api/v1/asr/health \
  -H "X-API-Key: test-key" \
  2>&1 | grep -i "kong\|route\|service"
```

## Monitoring

### Prometheus Metrics

```bash
# Get metrics
curl http://localhost:8001/metrics | grep kong_http_requests_total

# Scrape endpoint for Prometheus
# http://localhost:8001/metrics
```

### Key Metrics

- `kong_http_requests_total` - Total HTTP requests
- `kong_latency_ms` - Request latency
- `kong_requests_per_consumer` - Requests by consumer
- `kong_upstream_target_health` - Upstream health

## Language Routing

Language detection is performed from:
1. Request body: `config.language.sourceLanguage`
2. Query parameter: `lang` or `sourceLanguage`
3. Header: `X-Language` or `X-Source-Language`

Supported languages:
- `hi` - Hindi (Devanagari)
- `ta` - Tamil
- `te` - Telugu
- `en` - English
- `kn` - Kannada
- `ml` - Malayalam
- `bn` - Bengali
- `gu` - Gujarati
- `pa` - Punjabi
- `or` - Odia
- `ur` - Urdu (Arabic)

## Docker Commands

```bash
# Start Kong
docker-compose up -d kong

# Stop Kong
docker-compose stop kong

# Restart Kong
docker-compose restart kong

# Remove Kong
docker-compose down kong

# Execute command in Kong container
docker exec ai4v-kong-gateway kong --version

# Access Kong container shell
docker exec -it ai4v-kong-gateway sh
```

## Kong Admin API Operations

### Complete CRUD Examples

```bash
# CREATE Service
curl -X POST http://localhost:8001/services \
  -d "name=new-service" \
  -d "url=http://new-service:8080"

# READ Service
curl http://localhost:8001/services/new-service

# UPDATE Service
curl -X PATCH http://localhost:8001/services/new-service \
  -d "url=http://new-service:8081"

# DELETE Service
curl -X DELETE http://localhost:8001/services/new-service
```

