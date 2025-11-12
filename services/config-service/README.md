# Configuration Management Service

## Overview
The configuration management service provides centralized environment-specific configurations and a ZooKeeper-backed service registry. It integrates with PostgreSQL for persistence, Redis for caching, and Kafka for change notifications.

## Features
- Environment-specific configurations
- Service registry using ZooKeeper with ephemeral instances
- Dynamic updates via Kafka (`config-updates` topic)
- Redis caching for performance
- Audit trail for configuration changes
- Feature flags using Unleash and OpenFeature
- Boolean, string, integer, float, and object flag types
- User targeting and gradual rollouts
- Flag evaluation caching and audit trail

## Architecture
- ZooKeeper: service discovery and live instances (ephemeral nodes)
- PostgreSQL: persistent storage for configurations and registry audit
- Redis: caching configuration values and registry results
- Kafka: publish configuration change events
- Registry abstraction: pluggable `ServiceRegistryClient` interface

## API Endpoints
- Configuration (`/api/v1/config`)
  - POST `/` create configuration
  - GET `/{key}` fetch configuration by key (query: `environment`, `service_name`)
  - GET `/` list configurations (filters: `environment`, `service_name`, `keys[]`)
  - PUT `/{key}` update configuration
  - DELETE `/{key}` delete configuration
  - GET `/{key}/history` configuration history
  - POST `/bulk` bulk get
- Service Registry (`/api/v1/registry`)
  - POST `/register` register service instance
  - POST `/deregister` deregister instance
  - GET `/services` list all services
  - GET `/services/{service_name}` get instances
  - GET `/services/{service_name}/url` get balanced URL
  - POST `/services/{service_name}/health` trigger health check
  - GET `/discover/{service_name}` discover healthy instances
- Feature Flags (`/api/v1/feature-flags`)
  - POST `/evaluate` evaluate single flag
  - POST `/evaluate/boolean` evaluate boolean flag
  - POST `/evaluate/bulk` bulk evaluate flags
  - POST `/` create feature flag
  - GET `/{name}` get flag by name
  - GET `/` list flags
  - PUT `/{name}` update flag
  - DELETE `/{name}` delete flag
  - GET `/{name}/history` evaluation history
  - POST `/sync` sync from Unleash
- Health
  - GET `/health`, `/ready`, `/live`

## Configuration
Key environment variables (see `env.template`):
- DATABASE_URL, REDIS_HOST/PORT/PASSWORD
- KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_CONFIG_UPDATES
- ZOOKEEPER_HOSTS, ZOOKEEPER_BASE_PATH, ZOOKEEPER_CONNECTION_TIMEOUT, ZOOKEEPER_SESSION_TIMEOUT
- SERVICE_REGISTRY_ENABLED, SERVICE_HEALTH_CHECK_INTERVAL, SERVICE_INSTANCE_ID
- UNLEASH_URL, UNLEASH_APP_NAME, UNLEASH_INSTANCE_ID, UNLEASH_API_TOKEN
- UNLEASH_ENVIRONMENT, UNLEASH_REFRESH_INTERVAL, UNLEASH_METRICS_INTERVAL
- FEATURE_FLAG_CACHE_TTL, FEATURE_FLAG_FALLBACK_ENABLED

## Usage Examples
- Create configuration:
```bash
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{"key":"model_path","value":"/models/asr","environment":"development","service_name":"asr-service"}'
```
- Register service:
```bash
curl -X POST http://localhost:8082/api/v1/registry/register \
  -H 'Content-Type: application/json' \
  -d '{"service_name":"asr-service","service_url":"http://asr-service:8087","health_check_url":"http://asr-service:8087/health"}'
```
- Discover:
```bash
curl http://localhost:8082/api/v1/registry/discover/asr-service
```
- Evaluate feature flag:
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_name":"new-ui-enabled",
    "user_id":"user-123",
    "context":{"region":"us-west"},
    "default_value":false,
    "environment":"development"
  }'
```
- Evaluate boolean flag:
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate/boolean \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_name":"dark-mode",
    "user_id":"user-456",
    "default_value":false,
    "environment":"production"
  }'
```
- Sync flags from Unleash:
```bash
curl -X POST 'http://localhost:8082/api/v1/feature-flags/sync?environment=development'
```

## Development
- Install requirements: `pip install -r services/config_service/requirements.txt`
- Run locally: `uvicorn services.config_service.main:app --reload --port 8082`

## Deployment
- Ensure ZooKeeper and Kafka are healthy
- Configure `ZOOKEEPER_HOSTS`, `KAFKA_BOOTSTRAP_SERVERS`
- Consider enabling TLS and ACLs on ZooKeeper and Kafka; monitor registry health
- Ensure Unleash server is running and accessible
- Configure UNLEASH_URL and UNLEASH_API_TOKEN
- Run database migrations to create feature flag tables
- Access Unleash UI at http://localhost:4242 (default credentials: admin/unleash4all)
