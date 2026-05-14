# Configuration Management Service

## Overview
The configuration management service provides centralized environment-specific configurations and a ZooKeeper-backed service registry. It integrates with PostgreSQL for persistence, Redis for caching, and Kafka for change notifications.

## Features
- Environment-specific configurations
- Service registry using ZooKeeper with ephemeral instances
- Dynamic updates via Kafka (`config-updates` topic)
- Redis caching for performance
- Audit trail for configuration changes
- Internal health status contract for routing (Redis-backed)

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
- Internal (for inference routing)
  - GET `/internal/health-status?service_id={service_id}` get cached health state for a service
- Health
  - GET `/health`, `/ready`, `/live`

## Internal health status (routing contract)
Config-service runs periodic health probes (see `SERVICE_HEALTH_CHECK_ENABLED` / `SERVICE_HEALTH_CHECK_INTERVAL`) and writes a lightweight snapshot to Redis per service. The internal endpoint serves **cache-only** reads for low latency and to avoid DB queries or live checks on request.

### Endpoint
- GET `/internal/health-status?service_id={service_id}`

### Response fields
- `service_id`: service identifier (currently the service name in the registry)
- `state`: one of `healthy`, `degraded`, `unhealthy`, `unknown`
- `last_check`: UTC timestamp (ISO-8601) when the snapshot was written
- `total_instances`: number of instances observed for the service
- `healthy_instances`: number of instances that were healthy in the last probe

### State semantics
- `healthy`: all instances were healthy (and at least one instance exists)
- `degraded`: at least one instance is healthy, but not all
- `unhealthy`: instances exist but none are healthy
- `unknown`: no instances were observed (e.g., service not registered, registry unavailable)

### Performance characteristics
- Request path is **Redis GET + JSON parse only** (no DB query, no live probe).
- Snapshots have a TTL of approximately **2×** the probe interval (minimum 30s), so consumers can treat missing entries as unknown/stale.

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
## Development
- Install requirements: `pip install -r services/config_service/requirements.txt`
- Run locally: `uvicorn services.config_service.main:app --reload --port 8082`

## Deployment
- Ensure ZooKeeper and Kafka are healthy
- Configure `ZOOKEEPER_HOSTS`, `KAFKA_BOOTSTRAP_SERVERS`
- Consider enabling TLS and ACLs on ZooKeeper and Kafka; monitor registry health
