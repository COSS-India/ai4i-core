# Configuration Management Service

## Overview
The configuration management service provides centralized environment-specific configurations, feature flags with progressive rollout, and a ZooKeeper-backed service registry. It integrates with PostgreSQL for persistence, Redis for caching, and Kafka for change notifications.

## Features
- Environment-specific configurations
- Feature flags with rollout percentage and targeted users
- Service registry using ZooKeeper with ephemeral instances
- Dynamic updates via Kafka (`config-updates` topic)
- Redis caching for performance
- Audit trail for configuration changes

## Architecture
- ZooKeeper: service discovery and live instances (ephemeral nodes)
- PostgreSQL: persistent storage for configurations, flags, registry audit
- Redis: caching configuration values, flag evaluations, and registry results
- Kafka: publish configuration/flag change events
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
- Feature Flags (`/api/v1/feature-flags`)
  - POST `/` create flag
  - GET `/` list flags (filters: `environment`, `enabled`)
  - GET `/{name}` get flag
  - PUT `/{name}` update flag
  - DELETE `/{name}` delete flag
  - POST `/evaluate` evaluate user against a flag
  - POST `/evaluate/batch` batch evaluate
- Service Registry (`/api/v1/registry`)
  - POST `/register` register service instance
  - POST `/deregister` deregister instance
  - GET `/services` list all services
  - GET `/services/{service_name}` get instances
  - GET `/services/{service_name}/url` get balanced URL
  - POST `/services/{service_name}/health` trigger health check
  - GET `/discover/{service_name}` discover healthy instances
- Health
  - GET `/health`, `/ready`, `/live`

## Configuration
Key environment variables (see `env.template`):
- DATABASE_URL, REDIS_HOST/PORT/PASSWORD
- KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_CONFIG_UPDATES
- ZOOKEEPER_HOSTS, ZOOKEEPER_BASE_PATH, ZOOKEEPER_CONNECTION_TIMEOUT, ZOOKEEPER_SESSION_TIMEOUT
- SERVICE_REGISTRY_ENABLED, SERVICE_HEALTH_CHECK_INTERVAL, SERVICE_INSTANCE_ID

## Usage Examples
- Create configuration:
```bash
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{"key":"model_path","value":"/models/asr","environment":"development","service_name":"asr-service"}'
```
- Evaluate feature flag:
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"flag_name":"new_ui","user_id":"u123","environment":"development"}'
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

## Documentation

### Feature Flags
- [Feature Flags Implementation Guide](./docs/FEATURE_FLAGS.md) - Complete implementation details
- [Feature Flags Integration Guide](./docs/FEATURE_FLAGS_INTEGRATION.md) - How to integrate in microservices
- [Feature Flags Implementation Status](./FEATURE_FLAGS_IMPLEMENTATION.md) - Implementation status and testing

### Service Registry
- [Service Registry Integration](./docs/SERVICE_REGISTRY_INTEGRATION.md) - Integration guide
- [Service Registry Developer Guide](./docs/SERVICE_REGISTRY_DEVELOPER_GUIDE.md) - Developer documentation

### Testing
- [Quick Test Guide](./docs/QUICK_TEST_GUIDE.md) - Quick testing instructions
- [PostgreSQL E2E Testing](./docs/POSTGRES-E2E.md) - End-to-end testing guide
- [Health Monitoring Testing](./docs/TESTING_HEALTH_MONITORING.md) - Health check testing

## Development
- Install requirements: `pip install -r services/config_service/requirements.txt`
- Run locally: `uvicorn services.config_service.main:app --reload --port 8082`

## Deployment
- Ensure ZooKeeper and Kafka are healthy
- Configure `ZOOKEEPER_HOSTS`, `KAFKA_BOOTSTRAP_SERVERS`
- Consider enabling TLS and ACLs on ZooKeeper and Kafka; monitor registry health
