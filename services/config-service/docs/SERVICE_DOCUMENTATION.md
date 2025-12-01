# Config Service - Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Features](#features)
4. [Prerequisites](#prerequisites)
5. [Installation & Setup](#installation--setup)
6. [Configuration](#configuration)
7. [API Reference](#api-reference)
8. [Service Registry](#service-registry)
9. [Feature Flags](#feature-flags)
10. [Usage Examples](#usage-examples)
11. [Deployment](#deployment)
12. [Troubleshooting](#troubleshooting)
13. [Development](#development)

---

## Overview

The **Configuration Management Service** is a microservice that provides centralized configuration management, service discovery, and feature flag management for the platform. It integrates with ZooKeeper for service registry, PostgreSQL for persistence, Redis for caching, Kafka for event streaming, and Unleash for feature flag management.

### Key Capabilities

- **Centralized Configuration**: Environment-specific configurations for all microservices
- **Service Registry**: ZooKeeper-backed service discovery with health monitoring
- **Feature Flags**: Integration with Unleash and OpenFeature for progressive delivery
- **Dynamic Updates**: Real-time configuration updates via Kafka
- **Caching**: Redis-based caching for improved performance
- **Audit Trail**: Complete history of configuration changes

---

## Architecture

### System Architecture

```
Client → API Gateway → Config Service → PostgreSQL (Config Storage)
                              ↓
                        ZooKeeper (Service Registry)
                              ↓
                        Redis (Caching)
                              ↓
                        Kafka (Event Streaming)
                              ↓
                        Unleash (Feature Flags)
```

### Internal Architecture

The service follows a layered architecture pattern:

```
┌─────────────────────────────────────┐
│         FastAPI Application         │
│  (main.py - Entry Point)            │
└──────────────┬──────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐  ┌──────▼──────────┐
│   Routers   │  │   Services       │
│             │  │                 │
│ - Config    │  │ - ConfigService │
│ - Registry  │  │ - RegistryService│
│ - FeatureFlags│ │ - FeatureFlagService│
│ - Health    │  │ - HealthMonitorService│
└──────┬──────┘  └──────────────────┘
       │
┌──────▼──────┐
│ Repositories│
│             │
│ - ConfigRepository│
│ - RegistryRepository│
│ - FeatureFlagRepository│
└──────┬──────┘
       │
┌──────▼──────┐
│   Database  │
│  PostgreSQL │
└─────────────┘
```

### Components

1. **Routers** (`routers/`): FastAPI route handlers
   - `config_router.py`: Configuration management endpoints
   - `service_registry_router.py`: Service registry endpoints
   - `feature_flag_router.py`: Feature flag evaluation endpoints
   - `health_router.py`: Health check endpoints
2. **Services** (`services/`): Business logic
   - `config_service.py`: Configuration management logic
   - `service_registry_service.py`: Service registry operations
   - `feature_flag_service.py`: Feature flag evaluation
   - `health_monitor_service.py`: Service health monitoring
3. **Repositories** (`repositories/`): Data access layer
   - `config_repository.py`: Configuration persistence
   - `service_registry_repository.py`: Registry persistence
   - `feature_flag_repository.py`: Feature flag persistence
4. **Registry** (`registry/`): Service registry clients
   - `zookeeper_client.py`: ZooKeeper registry client
   - `base.py`: Base registry interface
5. **Providers** (`providers/`): Feature flag providers
   - `unleash_provider.py`: Unleash/OpenFeature provider

---

## Features

### Core Features

1. **Configuration Management**
   - Environment-specific configurations (development, staging, production)
   - Service-specific configurations
   - Dynamic configuration updates
   - Configuration history and audit trail
   - Bulk configuration operations

2. **Service Registry**
   - ZooKeeper-backed service discovery
   - Ephemeral instance registration
   - Automatic health monitoring
   - Load balancing support
   - Service instance discovery

3. **Feature Flags**
   - Integration with Unleash
   - OpenFeature standard compliance
   - Boolean, string, integer, float, and object flag types
   - User targeting and gradual rollouts
   - Flag evaluation caching
   - Multi-environment support

4. **Health Monitoring**
   - Periodic health checks for registered services
   - Automatic instance status updates
   - Retry logic with exponential backoff
   - Custom health check endpoints

5. **Event Streaming**
   - Kafka integration for configuration changes
   - Feature flag event publishing
   - Real-time notifications

---

## Prerequisites

### System Requirements

- **Python**: 3.10 or higher
- **PostgreSQL**: 15+ (for configuration and registry storage)
- **Redis**: 7+ (for caching)
- **ZooKeeper**: 3.7+ (for service registry)
- **Kafka**: 3.0+ (optional, for event streaming)
- **Unleash**: Latest (for feature flags)
- **Docker**: Optional, for containerized deployment

### Dependencies

Key Python packages (see `requirements.txt` for complete list):

- `fastapi>=0.104.0`: Web framework
- `uvicorn[standard]>=0.24.0`: ASGI server
- `sqlalchemy>=2.0.0`: ORM
- `asyncpg>=0.29.0`: PostgreSQL async driver
- `redis>=5.0.0`: Redis client
- `kazoo>=2.9.0`: ZooKeeper client
- `aiokafka>=0.10.0`: Kafka async client
- `openfeature-sdk>=1.0.0`: OpenFeature SDK
- `httpx>=0.25.0`: HTTP client

---

## Installation & Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd aiv4-core/services/config-service
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp env.template .env
# Edit .env with your configuration
```

### 4. Database Setup

Ensure PostgreSQL is running and the database schema is created. The service uses the `config_db` database and will create tables automatically on startup.

### 5. Redis Setup

Ensure Redis is running and accessible. Redis is used for caching configurations and feature flags.

### 6. ZooKeeper Setup

Ensure ZooKeeper is running and accessible. ZooKeeper is used for service registry.

### 7. Kafka Setup (Optional)

Ensure Kafka is running if you want to use event streaming for configuration changes.

### 8. Unleash Setup

Ensure Unleash server is running and accessible. Configure the API token with admin privileges.

### 9. Start Service

```bash
# Development
uvicorn main:app --host 0.0.0.0 --port 8082 --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8082 --workers 4
```

### 10. Verify Installation

```bash
curl http://localhost:8082/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "config-service",
  "version": "1.0.0"
}
```

---

## Configuration

### Environment Variables

All configuration is done via environment variables. See `env.template` for the complete list.

#### Service Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `config-service` |
| `SERVICE_PORT` | HTTP port | `8082` |
| `SERVICE_INSTANCE_ID` | Service instance ID | `config-service-1` |
| `LOG_LEVEL` | Logging level | `INFO` |

#### Database Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |

#### Redis Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_HOST` | Redis hostname | `redis` |
| `REDIS_PORT` | Redis port | `6379` |
| `REDIS_PASSWORD` | Redis password | `redis_secure_password_2024` |

#### ZooKeeper Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ZOOKEEPER_HOSTS` | ZooKeeper connection string | `zookeeper:2181` |
| `ZOOKEEPER_BASE_PATH` | Base path for services | `/services` |
| `ZOOKEEPER_CONNECTION_TIMEOUT` | Connection timeout (seconds) | `10` |
| `ZOOKEEPER_SESSION_TIMEOUT` | Session timeout (seconds) | `30` |

#### Kafka Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses | `kafka:9092` |
| `KAFKA_TOPIC_CONFIG_UPDATES` | Config update topic | `config-updates` |
| `FEATURE_FLAG_KAFKA_TOPIC` | Feature flag events topic | `feature-flag-events` |

#### Service Registry Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_REGISTRY_ENABLED` | Enable service registry | `true` |
| `SERVICE_HEALTH_CHECK_ENABLED` | Enable health monitoring | `true` |
| `SERVICE_HEALTH_CHECK_INTERVAL` | Health check interval (seconds) | `30` |
| `HEALTH_CHECK_TIMEOUT` | Health check timeout (seconds) | `3.0` |
| `HEALTH_CHECK_MAX_RETRIES` | Max retry attempts | `3` |
| `HEALTH_CHECK_INITIAL_RETRY_DELAY` | Initial retry delay (seconds) | `1.0` |
| `HEALTH_CHECK_MAX_RETRY_DELAY` | Max retry delay (seconds) | `30.0` |
| `HEALTH_CHECK_RETRY_BACKOFF` | Retry backoff multiplier | `2.0` |
| `HEALTH_CHECK_ADDITIONAL_ENDPOINTS` | Additional health endpoints | `/ready,/live` |

#### Unleash Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `UNLEASH_URL` | Unleash API URL | `http://unleash:4242/api` |
| `UNLEASH_APP_NAME` | Application name | `config-service` |
| `UNLEASH_INSTANCE_ID` | Instance identifier | `config-service-1` |
| `UNLEASH_API_TOKEN` | API token (Admin token required) | `*:*.unleash-insecure-api-token` |
| `UNLEASH_ENVIRONMENT` | SDK environment (optional) | - |
| `UNLEASH_REFRESH_INTERVAL` | SDK refresh interval (seconds) | `15` |
| `UNLEASH_METRICS_INTERVAL` | Metrics interval (seconds) | `60` |
| `UNLEASH_DISABLE_METRICS` | Disable metrics | `false` |
| `UNLEASH_AUTO_SYNC_ENABLED` | Enable periodic sync | `true` |
| `UNLEASH_AUTO_SYNC_ON_STARTUP` | Sync on startup | `false` |
| `UNLEASH_SYNC_INTERVAL` | Sync interval (seconds) | `30` |
| `UNLEASH_SYNC_ENVIRONMENTS` | Environments to sync | - |

#### Feature Flag Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `FEATURE_FLAG_CACHE_TTL` | Cache TTL (seconds) | `300` |
| `FEATURE_FLAG_FALLBACK_ENABLED` | Enable fallback | `true` |

#### Environment Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPPORTED_ENVIRONMENTS` | Supported environments | `development,staging,production` |
| `DEFAULT_ENVIRONMENT` | Default environment | `development` |

---

## API Reference

### Base URL

```
http://localhost:8082
```

### Endpoints

#### 1. Health Check

**GET** `/health`

Check service health and dependencies.

**Response:**
```json
{
  "status": "healthy",
  "service": "config-service",
  "version": "1.0.0"
}
```

#### 2. Root Endpoint

**GET** `/`

Get service information.

**Response:**
```json
{
  "service": "Configuration Management Service",
  "version": "1.0.0",
  "status": "running",
  "description": "Centralized configuration for microservices"
}
```

#### 3. Service Status

**GET** `/api/v1/config/status`

Get configuration service status and features.

**Response:**
```json
{
  "service": "config-service",
  "version": "v1",
  "status": "operational",
  "features": [
    "Environment-specific configurations",
    "Service discovery",
    "Dynamic configuration updates",
    "Configuration audit logging",
    "Feature flags with Unleash"
  ]
}
```

### Configuration Endpoints

#### 4. Create Configuration

**POST** `/api/v1/config`

Create a new configuration.

**Request Body:**
```json
{
  "key": "model_path",
  "value": "/models/asr",
  "environment": "development",
  "service_name": "asr-service",
  "description": "Path to ASR model files"
}
```

**Response:**
```json
{
  "key": "model_path",
  "value": "/models/asr",
  "environment": "development",
  "service_name": "asr-service",
  "description": "Path to ASR model files",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

#### 5. Get Configuration

**GET** `/api/v1/config/{key}`

Get configuration by key.

**Query Parameters:**
- `environment` (required): Environment name
- `service_name` (optional): Service name filter

**Response:**
```json
{
  "key": "model_path",
  "value": "/models/asr",
  "environment": "development",
  "service_name": "asr-service"
}
```

#### 6. List Configurations

**GET** `/api/v1/config`

List all configurations with optional filters.

**Query Parameters:**
- `environment` (optional): Filter by environment
- `service_name` (optional): Filter by service name
- `keys[]` (optional): Filter by specific keys

**Response:**
```json
[
  {
    "key": "model_path",
    "value": "/models/asr",
    "environment": "development",
    "service_name": "asr-service"
  }
]
```

#### 7. Update Configuration

**PUT** `/api/v1/config/{key}`

Update an existing configuration.

**Request Body:**
```json
{
  "value": "/models/asr-v2",
  "environment": "development",
  "service_name": "asr-service",
  "description": "Updated path to ASR model files"
}
```

#### 8. Delete Configuration

**DELETE** `/api/v1/config/{key}`

Delete a configuration.

**Query Parameters:**
- `environment` (required): Environment name
- `service_name` (optional): Service name filter

#### 9. Configuration History

**GET** `/api/v1/config/{key}/history`

Get configuration change history.

**Query Parameters:**
- `environment` (required): Environment name
- `service_name` (optional): Service name filter

**Response:**
```json
[
  {
    "key": "model_path",
    "value": "/models/asr-v2",
    "environment": "development",
    "service_name": "asr-service",
    "updated_at": "2024-01-02T00:00:00Z",
    "updated_by": "admin"
  },
  {
    "key": "model_path",
    "value": "/models/asr",
    "environment": "development",
    "service_name": "asr-service",
    "updated_at": "2024-01-01T00:00:00Z",
    "updated_by": "admin"
  }
]
```

#### 10. Bulk Get Configurations

**POST** `/api/v1/config/bulk`

Get multiple configurations in a single request.

**Request Body:**
```json
{
  "keys": ["model_path", "batch_size", "timeout"],
  "environment": "development",
  "service_name": "asr-service"
}
```

**Response:**
```json
{
  "model_path": "/models/asr",
  "batch_size": "32",
  "timeout": "20"
}
```

### Service Registry Endpoints

#### 11. Register Service

**POST** `/api/v1/registry/register`

Register a service instance in the registry.

**Request Body:**
```json
{
  "service_name": "asr-service",
  "service_url": "http://asr-service:8087",
  "health_check_url": "http://asr-service:8087/health",
  "metadata": {
    "instance_id": "asr-service-1",
    "version": "1.0.0"
  }
}
```

**Response:**
```json
{
  "instance_id": "asr-service-1",
  "service_name": "asr-service",
  "service_url": "http://asr-service:8087",
  "status": "registered"
}
```

#### 12. Deregister Service

**POST** `/api/v1/registry/deregister`

Deregister a service instance.

**Request Body:**
```json
{
  "service_name": "asr-service",
  "instance_id": "asr-service-1"
}
```

#### 13. List Services

**GET** `/api/v1/registry/services`

List all registered services.

**Response:**
```json
[
  {
    "service_name": "asr-service",
    "instances": [
      {
        "instance_id": "asr-service-1",
        "service_url": "http://asr-service:8087",
        "status": "healthy",
        "last_health_check": "2024-01-01T00:00:00Z"
      }
    ]
  }
]
```

#### 14. Get Service Instances

**GET** `/api/v1/registry/services/{service_name}`

Get all instances of a specific service.

**Response:**
```json
{
  "service_name": "asr-service",
  "instances": [
    {
      "instance_id": "asr-service-1",
      "service_url": "http://asr-service:8087",
      "status": "healthy",
      "last_health_check": "2024-01-01T00:00:00Z"
    }
  ]
}
```

#### 15. Get Service URL

**GET** `/api/v1/registry/services/{service_name}/url`

Get a balanced URL for a service (load balancing).

**Response:**
```json
{
  "service_name": "asr-service",
  "url": "http://asr-service:8087",
  "instance_id": "asr-service-1"
}
```

#### 16. Discover Service

**GET** `/api/v1/registry/discover/{service_name}`

Discover healthy instances of a service.

**Response:**
```json
{
  "service_name": "asr-service",
  "instances": [
    {
      "instance_id": "asr-service-1",
      "service_url": "http://asr-service:8087",
      "status": "healthy"
    }
  ]
}
```

#### 17. Trigger Health Check

**POST** `/api/v1/registry/services/{service_name}/health`

Manually trigger a health check for a service.

**Response:**
```json
{
  "service_name": "asr-service",
  "instances_checked": 2,
  "healthy_instances": 2,
  "unhealthy_instances": 0
}
```

### Feature Flag Endpoints

#### 18. Evaluate Feature Flag

**POST** `/api/v1/feature-flags/evaluate`

Evaluate a feature flag with context.

**Request Body:**
```json
{
  "flag_name": "new-ui-enabled",
  "user_id": "user-123",
  "context": {
    "region": "us-west",
    "environment": "development"
  },
  "default_value": false,
  "environment": "development"
}
```

**Response:**
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "reason": "TARGETING_MATCH",
  "variant": "enabled",
  "environment": "development"
}
```

#### 19. Evaluate Boolean Flag

**POST** `/api/v1/feature-flags/evaluate/boolean`

Evaluate a boolean feature flag.

**Request Body:**
```json
{
  "flag_name": "dark-mode",
  "user_id": "user-456",
  "default_value": false,
  "environment": "production"
}
```

**Response:**
```json
{
  "flag_name": "dark-mode",
  "value": true,
  "reason": "DEFAULT",
  "environment": "production"
}
```

#### 20. Bulk Evaluate Flags

**POST** `/api/v1/feature-flags/evaluate/bulk`

Evaluate multiple feature flags in a single request.

**Request Body:**
```json
{
  "flags": [
    {
      "flag_name": "new-ui-enabled",
      "default_value": false
    },
    {
      "flag_name": "dark-mode",
      "default_value": false
    }
  ],
  "user_id": "user-123",
  "context": {
    "region": "us-west"
  },
  "environment": "development"
}
```

**Response:**
```json
{
  "new-ui-enabled": {
    "value": true,
    "reason": "TARGETING_MATCH"
  },
  "dark-mode": {
    "value": false,
    "reason": "DEFAULT"
  }
}
```

#### 21. Get Feature Flag

**GET** `/api/v1/feature-flags/{name}`

Get feature flag details from Unleash (cached in Redis).

**Query Parameters:**
- `environment` (required): Environment name

**Response:**
```json
{
  "name": "new-ui-enabled",
  "enabled": true,
  "variants": [
    {
      "name": "enabled",
      "weight": 100
    }
  ],
  "strategies": [
    {
      "name": "default",
      "parameters": {}
    }
  ]
}
```

#### 22. List Feature Flags

**GET** `/api/v1/feature-flags`

List all feature flags from Unleash (cached in Redis).

**Query Parameters:**
- `environment` (required): Environment name

**Response:**
```json
[
  {
    "name": "new-ui-enabled",
    "enabled": true
  },
  {
    "name": "dark-mode",
    "enabled": false
  }
]
```

#### 23. Sync Feature Flags

**POST** `/api/v1/feature-flags/sync`

Refresh feature flag cache from Unleash.

**Query Parameters:**
- `environment` (required): Environment name

**Response:**
```json
{
  "environment": "development",
  "flags_synced": 15,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

## Service Registry

### Overview

The service registry provides service discovery capabilities using ZooKeeper as the backend. Services register themselves as ephemeral nodes, which are automatically removed when the service goes down.

### Registration Flow

1. Service starts and calls `/api/v1/registry/register`
2. Config service creates an ephemeral node in ZooKeeper
3. Health monitor periodically checks service health
4. If service becomes unhealthy, it's marked as such in the registry
5. When service shuts down, ZooKeeper automatically removes the ephemeral node

### Health Monitoring

The service includes automatic health monitoring that:
- Periodically checks registered services
- Updates service status based on health check results
- Supports retry logic with exponential backoff
- Checks multiple endpoints (`/health`, `/ready`, `/live`)

---

## Feature Flags

### Overview

The config service integrates with Unleash for feature flag management, providing:
- OpenFeature standard compliance
- Multiple flag types (boolean, string, integer, float, object)
- User targeting and gradual rollouts
- Multi-environment support
- Caching for performance

### Flag Management

Feature flags are managed in the Unleash UI. The config service provides evaluation endpoints that:
- Cache flag values in Redis
- Support user targeting
- Support gradual rollouts
- Provide fallback values

### Evaluation Flow

1. Client requests flag evaluation
2. Service checks Redis cache
3. If not cached, fetches from Unleash Admin API
4. Evaluates flag based on context and targeting rules
5. Caches result in Redis
6. Returns evaluation result

---

## Usage Examples

### Python Example - Configuration Management

```python
import requests

BASE_URL = "http://localhost:8082"

# Create configuration
config_data = {
    "key": "model_path",
    "value": "/models/asr",
    "environment": "development",
    "service_name": "asr-service"
}

response = requests.post(f"{BASE_URL}/api/v1/config", json=config_data)
print(response.json())

# Get configuration
response = requests.get(
    f"{BASE_URL}/api/v1/config/model_path",
    params={"environment": "development", "service_name": "asr-service"}
)
print(response.json())

# Update configuration
update_data = {
    "value": "/models/asr-v2",
    "environment": "development",
    "service_name": "asr-service"
}

response = requests.put(f"{BASE_URL}/api/v1/config/model_path", json=update_data)
print(response.json())
```

### Python Example - Service Registry

```python
# Register service
register_data = {
    "service_name": "asr-service",
    "service_url": "http://asr-service:8087",
    "health_check_url": "http://asr-service:8087/health",
    "metadata": {
        "instance_id": "asr-service-1",
        "version": "1.0.0"
    }
}

response = requests.post(f"{BASE_URL}/api/v1/registry/register", json=register_data)
print(response.json())

# Discover service
response = requests.get(f"{BASE_URL}/api/v1/registry/discover/asr-service")
instances = response.json()["instances"]
print(f"Found {len(instances)} healthy instances")
```

### Python Example - Feature Flags

```python
# Evaluate feature flag
flag_data = {
    "flag_name": "new-ui-enabled",
    "user_id": "user-123",
    "context": {
        "region": "us-west"
    },
    "default_value": False,
    "environment": "development"
}

response = requests.post(f"{BASE_URL}/api/v1/feature-flags/evaluate", json=flag_data)
result = response.json()
print(f"Flag {result['flag_name']}: {result['value']}")

# Bulk evaluate
bulk_data = {
    "flags": [
        {"flag_name": "new-ui-enabled", "default_value": False},
        {"flag_name": "dark-mode", "default_value": False}
    ],
    "user_id": "user-123",
    "environment": "development"
}

response = requests.post(f"{BASE_URL}/api/v1/feature-flags/evaluate/bulk", json=bulk_data)
results = response.json()
for flag_name, result in results.items():
    print(f"{flag_name}: {result['value']}")
```

---

## Deployment

### Docker Deployment

#### Build Image

```bash
docker build -t config-service:latest .
```

#### Run Container

```bash
docker run -d \
  --name config-service \
  -p 8082:8082 \
  --env-file .env \
  config-service:latest
```

### Production Considerations

1. **ZooKeeper**: Ensure ZooKeeper cluster is highly available
2. **Redis**: Use Redis cluster for high availability
3. **PostgreSQL**: Use connection pooling and replication
4. **Kafka**: Ensure Kafka cluster is properly configured
5. **Unleash**: Configure Unleash with proper authentication
6. **Security**: Enable TLS for all connections
7. **Monitoring**: Set up health checks and metrics collection

---

## Troubleshooting

### Common Issues

#### 1. ZooKeeper Connection Failed

**Problem**: Cannot connect to ZooKeeper

**Solutions**:
- Verify `ZOOKEEPER_HOSTS` is correct
- Check ZooKeeper is running
- Verify network connectivity
- Check ZooKeeper connection timeout settings

#### 2. Service Registration Fails

**Problem**: Service cannot register in registry

**Solutions**:
- Check ZooKeeper connection
- Verify service registry is enabled
- Check service instance ID is unique
- Review ZooKeeper logs

#### 3. Feature Flag Evaluation Fails

**Problem**: Feature flag evaluation returns errors

**Solutions**:
- Verify Unleash server is accessible
- Check `UNLEASH_API_TOKEN` has admin privileges
- Verify flag exists in Unleash
- Check Redis connection for caching
- Review Unleash logs

#### 4. Configuration Not Found

**Problem**: Configuration retrieval returns 404

**Solutions**:
- Verify configuration exists in database
- Check environment and service_name parameters
- Review configuration history
- Check database connection

---

## Development

### Project Structure

```
config-service/
├── main.py                 # FastAPI application entry point
├── routers/                # API route handlers
│   ├── config_router.py
│   ├── service_registry_router.py
│   ├── feature_flag_router.py
│   └── health_router.py
├── services/               # Business logic
│   ├── config_service.py
│   ├── service_registry_service.py
│   ├── feature_flag_service.py
│   └── health_monitor_service.py
├── repositories/           # Data access layer
│   ├── config_repository.py
│   ├── service_registry_repository.py
│   └── feature_flag_repository.py
├── registry/              # Service registry clients
│   ├── zookeeper_client.py
│   └── base.py
├── providers/             # Feature flag providers
│   └── unleash_provider.py
├── models/                # Pydantic and SQLAlchemy models
├── utils/                 # Utility functions
├── docs/                  # Additional documentation
├── requirements.txt        # Python dependencies
├── Dockerfile            # Docker image definition
└── env.template          # Environment variable template
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

### Additional Documentation

The service includes additional documentation in the `docs/` folder:

- `FEATURE_FLAGS.md`: Feature flags overview
- `FEATURE_FLAGS_ARCHITECTURE.md`: Feature flags architecture
- `FEATURE_FLAGS_INTEGRATION.md`: Integration guide
- `SERVICE_REGISTRY_DEVELOPER_GUIDE.md`: Service registry developer guide
- `SERVICE_REGISTRY_INTEGRATION.md`: Service registry integration
- `TESTING_HEALTH_MONITORING.md`: Health monitoring testing

---

## Additional Resources

- **API Documentation**: Available at `http://localhost:8082/docs` (Swagger UI)
- **ReDoc**: Available at `http://localhost:8082/redoc`
- **OpenAPI Spec**: Available at `http://localhost:8082/openapi.json`
- **Unleash UI**: Available at `http://localhost:4242` (default credentials: admin/unleash4all)

