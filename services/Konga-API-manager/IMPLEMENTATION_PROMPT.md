# Kong API Gateway Implementation Prompt for AIV4-Core

## Context and Architecture Overview

You are implementing **Kong API Gateway** as the centralized entry point for all API traffic in the AIV4-Core microservices architecture. The system currently has:

### Existing Microservices
- **auth-service** (port 8081): Authentication and authorization
- **config-service** (port 8082): Configuration management
- **metrics-service** (port 8083): Metrics collection
- **telemetry-service** (port 8084): Telemetry data
- **alerting-service** (port 8085): Alert management
- **dashboard-service** (port 8086): Dashboard UI backend
- **asr-service** (port 8087): Automatic Speech Recognition
- **tts-service** (port 8088): Text-to-Speech synthesis
- **nmt-service** (port 8089): Neural Machine Translation
- **pipeline-service** (port 8090): Multi-step AI pipeline orchestration

### Current Infrastructure
- **PostgreSQL** (port 5434): Database for all services
- **Redis** (port 6381): Caching and session storage
- **InfluxDB** (port 8089): Time-series metrics
- **Elasticsearch** (port 9203): Search and logging
- **Kafka** (port 9093): Message queue

### Existing API Gateway
Currently, there's a FastAPI-based API Gateway (`api-gateway-service`) that handles routing. **This will be replaced/replaced by Kong Gateway**, which provides better enterprise features and performance.

---

## Objective

Implement Kong API Gateway as the centralized entry point that provides:

1. **Intelligent Request Routing** - Language-aware routing to select appropriate models/services
2. **Request Routing & Load Balancing** - Efficient request distribution across service instances
3. **Rate Limiting & Throttling** - Protect services from overload
4. **Authentication & Authorization** - Centralized auth management
5. **Request/Response Transformation** - Modify requests/responses as needed
6. **API Versioning Management** - Support multiple API versions

---

## Implementation Steps

### 1️⃣ Gateway Setup

#### 1.1 Kong Installation & Configuration

**Location**: `services/Kong-API-manager/`

**Required Files**:
- `kong.yml` - Kong declarative configuration
- `docker-compose.yml` - Kong services definition
- `kong.conf` - Kong server configuration (if using DB mode)
- `Dockerfile` (optional) - Custom Kong image

**Configuration Requirements**:

```yaml
# Kong should run in DB-less mode (declarative config) for simplicity
# OR use PostgreSQL for persistent storage

# Database configuration (if using DB mode)
database: postgres
pg_host: postgres
pg_port: 5432
pg_database: kong
pg_user: ${POSTGRES_USER}
pg_password: ${POSTGRES_PASSWORD}

# Gateway ports
proxy_listen: 0.0.0.0:8000
admin_api_listen: 0.0.0.0:8001
proxy_error_log: /dev/stderr
admin_error_log: /dev/stderr
proxy_access_log: /dev/stdout
admin_access_log: /dev/stdout
```

#### 1.2 Docker Compose Integration

Add Kong services to root `docker-compose.yml`:

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
  volumes:
    - ./services/Kong-API-manager/kong.yml:/kong/kong.yml:ro
  networks:
    - microservices-network
  depends_on:
    - postgres
    - redis
  healthcheck:
    test: ["CMD", "kong", "health"]
    interval: 10s
    timeout: 10s
    retries: 5
  restart: unless-stopped

# Optional: Kong Manager (Web UI)
kong-manager:
  image: kong/kong-manager:3.4
  container_name: ai4v-kong-manager
  ports:
    - "8002:8002"
  environment:
    KONG_ADMIN_API_URL: http://kong:8001
    KONG_ADMIN_API_URI: /admin-api
  depends_on:
    - kong
  networks:
    - microservices-network
  restart: unless-stopped
```

---

### 2️⃣ Intelligent Request Routing

#### 2.1 Language Detection & Routing Logic

**Requirement**: Implement intelligent routing that:
- Detects language from request payload (JSON body or query params)
- Routes to appropriate service/model based on detected language
- Supports fallback routing if language detection fails

**Implementation Approach**:

1. **Create a Kong Plugin** for language detection (`language-router` plugin)
   - Location: `services/Kong-API-manager/plugins/language-router.lua`
   - Extract language from:
     - Request body JSON: `config.language.sourceLanguage`
     - Query parameter: `lang` or `sourceLanguage`
     - Header: `X-Language` or `X-Source-Language`
   - Use existing language detection logic from `nmt-service/services/language_detection_service.py`

2. **Service Mapping by Language**:
   ```lua
   -- Language to service mapping
   local language_service_map = {
     ["hi"] = "asr-hindi-service",    -- Hindi ASR model
     ["ta"] = "asr-tamil-service",     -- Tamil ASR model
     ["te"] = "asr-telugu-service",    -- Telugu ASR model
     ["en"] = "asr-english-service",   -- English ASR model
     -- Add more language mappings
   }
   ```

3. **Dynamic Upstream Selection**:
   - Use Kong's `request-termination` or custom plugin to change upstream based on detected language
   - Update route dynamically using Kong's Admin API from within plugin

**Kong Configuration for Language Routing**:

```yaml
# In kong.yml
services:
  # ASR Service with language-aware routing
  - name: asr-service
    url: http://asr-service:8087
    routes:
      - name: asr-route
        paths:
          - /api/v1/asr
        strip_path: true
        plugins:
          - name: language-router  # Custom plugin
            config:
              language_field: "config.language.sourceLanguage"
              fallback_service: "asr-service"
              language_mappings:
                hi: "asr-service"
                ta: "asr-service"
                en: "asr-service"
                # Maps to same service but can route to different models
```

#### 2.2 Model Selection Based on Language

For services that support multiple models (ASR, TTS, NMT), route to appropriate model endpoints:

```yaml
plugins:
  - name: request-transformer
    config:
      replace:
        uri: /api/v1/asr/inference
      body:
        - config.serviceId: $(language_service_map[detected_language])
```

---

### 3️⃣ Load Balancing

#### 3.1 Configure Upstreams with Load Balancing

**Requirement**: Each service should have an upstream with multiple targets for load balancing.

**Implementation**:

```yaml
# In kong.yml
upstreams:
  - name: asr-service-upstream
    healthchecks:
      active:
        http_path: /api/v1/asr/health
        healthy:
          interval: 10
          successes: 2
        unhealthy:
          interval: 10
          http_failures: 3
    targets:
      - target: asr-service:8087
        weight: 100
      # Add more targets if multiple instances available

  - name: tts-service-upstream
    healthchecks:
      active:
        http_path: /api/v1/tts/health
        healthy:
          interval: 10
          successes: 2
        unhealthy:
          interval: 10
          http_failures: 3
    targets:
      - target: tts-service:8088
        weight: 100

# Update services to use upstreams
services:
  - name: asr-service
    url: http://asr-service-upstream
    # ... rest of config
```

**Load Balancing Algorithms**:
- Default: Round-robin
- Options: Consistent hashing (use `hash_on` in upstream config)

---

### 4️⃣ Rate Limiting & Throttling

#### 4.1 Global Rate Limiting

**Requirement**: Apply rate limits at different levels:
- Per consumer (API key)
- Per service
- Per route
- Global

**Configuration**:

```yaml
# Global rate limiting plugin
plugins:
  - name: rate-limiting
    config:
      minute: 1000
      hour: 10000
      day: 100000
      policy: local  # Use 'cluster' for Redis-based distributed limiting
      redis:
        host: redis
        port: 6379
        password: ${REDIS_PASSWORD}
        database: 1
        timeout: 2000
        ssl: false
        ssl_verify: false

# Per-service rate limiting
services:
  - name: asr-service
    plugins:
      - name: rate-limiting
        config:
          minute: 100
          hour: 1000
          limit_by: consumer
          policy: cluster  # Distributed using Redis
          redis:
            host: redis
            port: 6379

# Per-consumer rate limiting (fine-grained)
# Applied via consumer-specific plugins
```

#### 4.2 Request Throttling (Sliding Window)

Use Kong's `rate-limiting-advanced` plugin for more sophisticated throttling:

```yaml
plugins:
  - name: rate-limiting-advanced
    config:
      limit:
        - 100
      window_size:
        - 60
      sync_rate: 10
      window_type: sliding
      identifier: consumer
      strategy: cluster  # Redis-based
      redis:
        host: redis
        port: 6379
```

---

### 5️⃣ Authentication & Authorization

#### 5.1 API Key Authentication

**Requirement**: Implement API key-based authentication for all AI services.

**Configuration**:

```yaml
# Create consumers (API key users)
consumers:
  - username: ai4voice-client
    tags:
      - production
      - ai-services
    keyauth_credentials:
      - key: ${AI4VOICE_API_KEY}
        tags:
          - asr
          - tts
          - nmt

  - username: pipeline-client
    keyauth_credentials:
      - key: ${PIPELINE_API_KEY}

# Apply key-auth plugin to services
services:
  - name: asr-service
    plugins:
      - name: key-auth
        config:
          key_names:
            - apikey
            - X-API-Key
          key_in_body: false
          key_in_header: true
          key_in_query: true
          hide_credentials: true

  # Public endpoints (no auth)
  - name: auth-service
    plugins:
      - name: cors
        config:
          origins:
            - "*"
```

#### 5.2 JWT Authentication (Optional)

For user-based authentication:

```yaml
plugins:
  - name: jwt
    config:
      uri_param_names:
        - jwt
      cookie_names:
        - jwt
      header_names:
        - Authorization
      claims_to_verify:
        - exp
        - nbf
      key_claim_name: kid
      secret_is_base64: false
      run_on_preflight: true

consumers:
  - username: user-client
    jwt_secrets:
      - key: user-jwt-secret
        secret: ${JWT_SECRET}
        algorithm: HS256
```

#### 5.3 OAuth2 Plugin (Optional)

For third-party OAuth integration:

```yaml
plugins:
  - name: oauth2
    config:
      scopes:
        - read
        - write
      mandatory_scope: true
      token_expiration: 3600
      enable_authorization_code: true
      enable_client_credentials: true
      enable_implicit_grant: false
```

---

### 6️⃣ Request/Response Transformation

#### 6.1 Request Transformation

**Use Cases**:
- Add language detection header
- Normalize request format
- Add correlation IDs
- Transform API version in URL

**Configuration**:

```yaml
plugins:
  - name: request-transformer
    config:
      add:
        headers:
          - "X-Forwarded-For:$(proxy_proxy_address)"
          - "X-Real-IP:$(proxy_proxy_address)"
          - "X-Correlation-ID:$(uuid)"
          - "X-Request-ID:$(uuid)"
        body:
          - "gateway.timestamp:$(now)"
      remove:
        headers:
          - "X-API-Key"  # Hide API key from backend
      replace:
        headers:
          - "Host:asr-service:8087"
      append:
        headers:
          - "X-Language-Source:Gateway"
```

#### 6.2 Response Transformation

**Use Cases**:
- Add CORS headers
- Transform error responses
- Add response metadata
- Remove sensitive headers

**Configuration**:

```yaml
plugins:
  - name: response-transformer
    config:
      add:
        headers:
          - "X-Served-By:Kong-Gateway"
          - "X-Gateway-Version:1.0"
          - "X-Response-Time:$(latency)"
        json:
          - "meta.gateway:kong"
          - "meta.timestamp:$(now)"
      remove:
        headers:
          - "X-Internal-Id"  # Hide internal IDs
        json:
          - "internal.debug"
      replace:
        json:
          - "version:v1"
```

---

### 7️⃣ API Versioning

#### 7.1 Multiple API Versions

**Requirement**: Support multiple API versions (v1, v2) with version-specific routing.

**Implementation**:

```yaml
# Version 1 routes
services:
  - name: asr-service-v1
    url: http://asr-service:8087
    routes:
      - name: asr-v1-route
        paths:
          - /api/v1/asr
        strip_path: true
        plugins:
          - name: response-transformer
            config:
              replace:
                json:
                  - "api_version:v1"

# Version 2 routes (future)
  - name: asr-service-v2
    url: http://asr-service-v2:8087
    routes:
      - name: asr-v2-route
        paths:
          - /api/v2/asr
        strip_path: true
        plugins:
          - name: response-transformer
            config:
              replace:
                json:
                  - "api_version:v2"

# Default version routing
  - name: asr-service-default
    url: http://asr-service:8087
    routes:
      - name: asr-default-route
        paths:
          - /api/asr  # Default to latest version
        strip_path: true
        plugins:
          - name: request-transformer
            config:
              replace:
                uri: /api/v1/asr  # Redirect to v1
```

#### 7.2 Version Header Support

Allow versioning via headers:

```yaml
plugins:
  - name: request-transformer
    config:
      replace:
        uri: $(headers["X-API-Version"] ? "/api/" + headers["X-API-Version"] + "/asr" : "/api/v1/asr")
```

---

## Complete Kong Configuration Structure

### Directory Structure

```
services/Kong-API-manager/
├── kong.yml                    # Main declarative config
├── kong.conf                    # Kong server config (if DB mode)
├── docker-compose.yml           # Kong services
├── plugins/
│   ├── language-router.lua      # Custom language routing plugin
│   └── request-enricher.lua     # Custom request enrichment plugin
├── init/
│   └── init-kong.sh            # Initialization script
└── README.md                    # Documentation
```

### Complete kong.yml Template

```yaml
_format_version: "3.0"
_transform: true

# ============================================
# UPSTREAMS - Service pools with load balancing
# ============================================
upstreams:
  - name: auth-service-upstream
    healthchecks:
      active:
        http_path: /health
        healthy:
          interval: 10
          successes: 2
        unhealthy:
          interval: 10
          http_failures: 3

  - name: asr-service-upstream
    healthchecks:
      active:
        http_path: /api/v1/asr/health
        healthy:
          interval: 10
          successes: 2
        unhealthy:
          interval: 10
          http_failures: 3
    algorithm: round-robin

  - name: tts-service-upstream
    healthchecks:
      active:
        http_path: /api/v1/tts/health
    algorithm: round-robin

  - name: nmt-service-upstream
    healthchecks:
      active:
        http_path: /api/v1/nmt/health
    algorithm: round-robin

  - name: pipeline-service-upstream
    healthchecks:
      active:
        http_path: /api/v1/pipeline/health
    algorithm: round-robin

# ============================================
# TARGETS - Backend service instances
# ============================================
targets:
  - target: auth-service:8081
    upstream: auth-service-upstream
    weight: 100

  - target: asr-service:8087
    upstream: asr-service-upstream
    weight: 100

  - target: tts-service:8088
    upstream: tts-service-upstream
    weight: 100

  - target: nmt-service:8089
    upstream: nmt-service-upstream
    weight: 100

  - target: pipeline-service:8090
    upstream: pipeline-service-upstream
    weight: 100

# ============================================
# SERVICES - API service definitions
# ============================================
services:
  # Authentication Service (Public)
  - name: auth-service
    url: http://auth-service-upstream
    routes:
      - name: auth-route
        paths:
          - /api/v1/auth
        strip_path: true
        methods:
          - GET
          - POST
          - PUT
          - DELETE
        plugins:
          - name: cors
            config:
              origins:
                - "*"
              methods:
                - GET
                - POST
                - PUT
                - DELETE
              credentials: true
          - name: rate-limiting
            config:
              minute: 200
              hour: 2000
              policy: cluster
              redis:
                host: redis
                port: 6379

  # ASR Service
  - name: asr-service
    url: http://asr-service-upstream
    routes:
      - name: asr-route
        paths:
          - /api/v1/asr
        strip_path: true
        plugins:
          - name: key-auth
            config:
              key_names:
                - apikey
                - X-API-Key
              hide_credentials: true
          - name: rate-limiting
            config:
              minute: 100
              hour: 1000
              limit_by: consumer
              policy: cluster
              redis:
                host: redis
                port: 6379
          - name: request-transformer
            config:
              add:
                headers:
                  - "X-Correlation-ID:$(uuid)"
                  - "X-Request-ID:$(uuid)"
          - name: response-transformer
            config:
              add:
                headers:
                  - "X-Served-By:Kong-ASR"
          - name: language-router  # Custom plugin
            config:
              language_field: "config.language.sourceLanguage"
              fallback_service: "asr-service"

  # TTS Service
  - name: tts-service
    url: http://tts-service-upstream
    routes:
      - name: tts-route
        paths:
          - /api/v1/tts
        strip_path: true
        plugins:
          - name: key-auth
          - name: rate-limiting
            config:
              minute: 100
              hour: 1000
              limit_by: consumer
          - name: request-transformer
            config:
              add:
                headers:
                  - "X-Correlation-ID:$(uuid)"

  # NMT Service
  - name: nmt-service
    url: http://nmt-service-upstream
    routes:
      - name: nmt-route
        paths:
          - /api/v1/nmt
        strip_path: true
        plugins:
          - name: key-auth
          - name: rate-limiting
            config:
              minute: 150
              hour: 1500
              limit_by: consumer
          - name: language-router
            config:
              language_field: "config.language.sourceLanguage"

  # Pipeline Service
  - name: pipeline-service
    url: http://pipeline-service-upstream
    routes:
      - name: pipeline-route
        paths:
          - /api/v1/pipeline
        strip_path: true
        plugins:
          - name: key-auth
          - name: rate-limiting
            config:
              minute: 50
              hour: 500
              limit_by: consumer

  # Config Service
  - name: config-service
    url: http://config-service:8082
    routes:
      - name: config-route
        paths:
          - /api/v1/config
        strip_path: true
        plugins:
          - name: key-auth
          - name: rate-limiting
            config:
              minute: 200
              hour: 2000

# ============================================
# CONSUMERS - API key users
# ============================================
consumers:
  - username: ai4voice-client
    tags:
      - production
    keyauth_credentials:
      - key: ${AI4VOICE_API_KEY}
        tags:
          - ai-services
      - key: ${ASR_API_KEY}
        tags:
          - asr-only

  - username: developer-client
    keyauth_credentials:
      - key: ${DEVELOPER_API_KEY}
        tags:
          - development

# ============================================
# GLOBAL PLUGINS - Applied to all requests
# ============================================
plugins:
  - name: prometheus
    config:
      per_consumer: true
      status_code_metrics: true
      latency_metrics: true
      bandwidth_metrics: true
      upstream_health_metrics: true

  - name: correlation-id
    config:
      header_name: X-Correlation-ID
      echo_downstream: true

  - name: file-log
    config:
      path: /tmp/kong-access.log
      reopen: true

# ============================================
# CUSTOM PLUGINS - Language routing
# ============================================
# Note: Custom plugins need to be mounted in Kong container
```

---

## Implementation Checklist

### Phase 1: Basic Setup
- [ ] Install Kong Gateway (Docker container)
- [ ] Configure Kong in DB-less mode
- [ ] Create basic `kong.yml` with service routes
- [ ] Integrate Kong into `docker-compose.yml`
- [ ] Test basic routing to all microservices

### Phase 2: Core Features
- [ ] Implement load balancing with upstreams
- [ ] Configure health checks for all services
- [ ] Add rate limiting (global and per-service)
- [ ] Implement API key authentication
- [ ] Add request/response transformation
- [ ] Configure CORS

### Phase 3: Advanced Features
- [ ] Create custom language-router plugin
- [ ] Implement intelligent language-based routing
- [ ] Add API versioning support
- [ ] Configure JWT authentication (optional)
- [ ] Set up Kong Manager dashboard
- [ ] Add Prometheus metrics integration

### Phase 4: Security & Monitoring
- [ ] Configure SSL/TLS termination
- [ ] Add IP whitelisting/blacklisting
- [ ] Set up distributed rate limiting (Redis)
- [ ] Configure request logging
- [ ] Add error handling and custom error pages

### Phase 5: Testing & Documentation
- [ ] Write integration tests for routing
- [ ] Test load balancing scenarios
- [ ] Verify rate limiting behavior
- [ ] Test authentication flows
- [ ] Document all routes and configurations
- [ ] Create API usage examples

---

## Testing Requirements

### Integration Tests

Create test files in `services/Kong-API-manager/tests/`:

1. **Routing Tests** (`test_routing.py`):
   ```python
   # Test: Route /api/v1/asr to asr-service
   # Test: Route /api/v1/tts to tts-service
   # Test: Route /api/v1/auth to auth-service
   # Test: 404 for unknown routes
   ```

2. **Authentication Tests** (`test_auth.py`):
   ```python
   # Test: Request without API key returns 401
   # Test: Request with valid API key succeeds
   # Test: Request with invalid API key returns 401
   ```

3. **Rate Limiting Tests** (`test_rate_limiting.py`):
   ```python
   # Test: Exceeding rate limit returns 429
   # Test: Rate limit resets after window
   ```

4. **Language Routing Tests** (`test_language_routing.py`):
   ```python
   # Test: Hindi text routes to Hindi model
   # Test: Tamil text routes to Tamil model
   # Test: Fallback to default on detection failure
   ```

5. **Load Balancing Tests** (`test_load_balancing.py`):
   ```python
   # Test: Requests distributed across instances
   # Test: Unhealthy instances removed from pool
   ```

---

## Documentation Requirements

### API Documentation

Create `services/Kong-API-manager/API_DOCUMENTATION.md`:

1. **Routes Table**:
   | Route | Service | Auth Required | Rate Limit |
   |-------|---------|---------------|------------|
   | `/api/v1/auth/*` | auth-service | No | 200/min |
   | `/api/v1/asr/*` | asr-service | Yes | 100/min |
   | `/api/v1/tts/*` | tts-service | Yes | 100/min |
   | `/api/v1/nmt/*` | nmt-service | Yes | 150/min |

2. **Authentication Guide**:
   - How to obtain API keys
   - How to use API keys (header, query param)
   - Token refresh flow

3. **Rate Limiting Guide**:
   - Limits per endpoint
   - How to check rate limit headers
   - Handling 429 responses

4. **Language Routing Guide**:
   - Supported languages
   - How language detection works
   - Overriding language detection

### Configuration Examples

Create `services/Kong-API-manager/CONFIG_EXAMPLES.md`:
- Example API key creation
- Example service addition
- Example plugin configuration
- Example rate limit configuration

---

## Migration from FastAPI Gateway

### Migration Steps

1. **Update Frontend Configuration**:
   - Change `NEXT_PUBLIC_API_URL` from `http://api-gateway-service:8080` to `http://kong:8000`

2. **Update Service URLs**:
   - All services should continue using their original ports internally
   - Kong routes to these services

3. **API Key Migration**:
   - Migrate existing API keys to Kong consumers
   - Update client applications to use Kong endpoints

4. **Deployment**:
   - Deploy Kong alongside existing services
   - Test all endpoints through Kong
   - Once verified, deprecate FastAPI gateway (or keep as backup)

---

## Environment Variables

Add to root `.env` and `env.template`:

```bash
# Kong Gateway
KONG_DATABASE=off
KONG_DECLARATIVE_CONFIG=/kong/kong.yml
KONG_PROXY_LISTEN=0.0.0.0:8000
KONG_ADMIN_LISTEN=0.0.0.0:8001

# Kong Manager (optional)
KONG_MANAGER_URL=http://kong-manager:8002

# API Keys for Consumers
AI4VOICE_API_KEY=your-secure-api-key-here
ASR_API_KEY=your-asr-api-key-here
TTS_API_KEY=your-tts-api-key-here
NMT_API_KEY=your-nmt-api-key-here
PIPELINE_API_KEY=your-pipeline-api-key-here
DEVELOPER_API_KEY=your-developer-api-key-here

# JWT Secret (if using JWT auth)
JWT_SECRET=your-jwt-secret-here
```

---

## Expected Outcome

After implementation:

✅ **All requests enter through Kong Gateway** at port 8000  
✅ **Routing is intelligent** - Language-aware model selection  
✅ **Security centralized** - Authentication, authorization, rate limiting  
✅ **Performance optimized** - Load balancing, health checks, caching  
✅ **Governance enabled** - API versioning, request/response transformation  
✅ **Observability** - Metrics, logging, tracing  
✅ **Easy extensibility** - Add new services by adding routes in `kong.yml`

---

## Success Criteria

1. ✅ All existing API endpoints accessible through Kong
2. ✅ Language-based routing working for ASR/TTS/NMT services
3. ✅ Rate limiting prevents service overload
4. ✅ API key authentication working
5. ✅ Load balancing distributes requests across instances
6. ✅ Health checks remove unhealthy instances automatically
7. ✅ Request/response transformation working
8. ✅ API versioning supported
9. ✅ Integration tests passing
10. ✅ Documentation complete

---

## Additional Considerations

### Performance
- Use Redis for distributed rate limiting
- Enable connection pooling
- Consider caching for static responses

### Security
- Implement IP whitelisting for admin API
- Use HTTPS in production
- Rotate API keys regularly
- Monitor for suspicious traffic

### Monitoring
- Integrate with Prometheus for metrics
- Set up alerts for high error rates
- Monitor rate limit violations
- Track API usage by consumer

### Scaling
- Kong can be scaled horizontally
- Use DB mode for multi-instance deployments
- Consider Kong Mesh for service mesh

---

## Support and Resources

- **Kong Documentation**: https://docs.konghq.com/
- **Kong Plugin Development**: https://docs.konghq.com/gateway/latest/plugin-development/
- **Kong Admin API**: https://docs.konghq.com/gateway/latest/admin-api/
- **Kong Declarative Config**: https://docs.konghq.com/gateway/latest/declarative-config/

---

**Implementation Priority**: High  
**Estimated Effort**: 5-7 days  
**Complexity**: Medium-High  
**Dependencies**: Kong Docker image, Redis, PostgreSQL (optional)

This prompt provides a complete blueprint for implementing Kong API Gateway in the AIV4-Core architecture. Follow the steps sequentially, test thoroughly, and document everything.

