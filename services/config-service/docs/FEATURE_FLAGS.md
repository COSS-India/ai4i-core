# Feature Flags with Unleash and OpenFeature

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
  - [Components](#components)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
- [Usage](#usage)
  - [Creating Flags in Unleash](#creating-flags-in-unleash)
  - [Evaluating Flags](#evaluating-flags)
  - [Flag Types](#flag-types)
- [Integration Patterns](#integration-patterns)
  - [For Other Services](#for-other-services)
  - [Context Mapping](#context-mapping)
- [Operational Guide](#operational-guide)
  - [Monitoring](#monitoring)
  - [Troubleshooting](#troubleshooting)
  - [Best Practices](#best-practices)
- [API Reference](#api-reference)
- [Implementation Details](#implementation-details)
- [Examples](#examples)
- [Advanced Topics](#advanced-topics)

## Overview

The feature flag system uses a dual-schema approach:
- **Unleash Server**: Acts as the source of truth for flag definitions, strategies, and evaluations. Uses a dedicated 'unleash' database in the shared PostgreSQL instance.
- **OpenFeature SDK**: Provides vendor-neutral abstraction layer for flag evaluation, preventing lock-in to any specific provider.
- **Custom Provider**: Bridges Unleash and OpenFeature, enabling seamless integration.
- **Local Database**: Caches flag definitions and maintains audit trail of all evaluations.
- **Redis**: Caches evaluation results for performance.
- **Kafka**: Publishes flag change events for real-time updates.

## Architecture

### Components

1. **Unleash Server** (Port 4242)
   - Flag definitions and strategies
   - Uses shared PostgreSQL with 'unleash' database
   - Provides web UI for flag management
   - REST API for flag operations

2. **OpenFeature SDK**
   - Vendor-neutral evaluation API
   - Supports multiple providers via domains
   - Consistent interface across services

3. **Custom Unleash Provider** (`providers/unleash_provider.py`)
   - Wraps Unleash Python SDK (`UnleashClient`)
   - Implements OpenFeature `AbstractProvider` interface
   - Handles context mapping from OpenFeature to Unleash format
   - Supports all flag types: boolean, string, integer, float, object (JSON)
   - Maps `targeting_key` to Unleash `userId`
   - Passes all `attributes` as Unleash context properties
   - Handles error cases gracefully with fallback to default values

4. **Local Database (config_db)**
   - `feature_flags`: Cached flag definitions with metadata
     - Stores flag name, description, enabled status, environment
     - Tracks evaluation count and last evaluated timestamp
     - Maintains sync status with Unleash (`last_synced_at`)
   - `feature_flag_evaluations`: Complete audit trail of all evaluations
     - Records user_id, context, result, variant, evaluated_value
     - Stores evaluation reason (TARGETING_MATCH, DEFAULT, ERROR)
     - Timestamped for analytics and debugging

5. **Redis Cache**
   - Evaluation result caching (TTL: 300s by default, configurable)
   - Cache key format: `feature_flag:eval:{environment}:{flag_name}:{user_id}:{context_hash}`
   - Context attributes are hashed for consistent cache keys
   - Automatic cache invalidation on flag updates
   - Reduces database load and improves response times

6. **Kafka Events**
   - Event types: `FEATURE_FLAG_CREATED`, `FEATURE_FLAG_UPDATED`, `FEATURE_FLAG_DELETED`, `FEATURE_FLAG_EVALUATED`
   - Published to topic: `feature-flag-events` (configurable)
   - Evaluation events include flag_name, user_id, environment, value, reason
   - Enables real-time cache invalidation and analytics

## Setup

### Prerequisites

- Docker and Docker Compose
- PostgreSQL (shared instance)
- Redis (for caching)
- Kafka (for events)

### Installation

1. **Start Infrastructure**
   ```bash
   docker-compose up -d postgres unleash redis kafka
   ```

2. **Access Unleash UI**
   - URL: http://localhost:4242
   - Default credentials: admin/unleash4all
   - Create API token in Settings → API Access

3. **Configure Environment Variables**
   
   Required variables:
   ```bash
   UNLEASH_URL=http://unleash:4242/api
   UNLEASH_APP_NAME=config-service
   UNLEASH_INSTANCE_ID=config-service-1
   UNLEASH_API_TOKEN=your-api-token-here
   UNLEASH_ENVIRONMENT=development
   ```
   
   Optional variables (with defaults):
   ```bash
   UNLEASH_REFRESH_INTERVAL=15          # Flag refresh interval in seconds
   UNLEASH_METRICS_INTERVAL=60          # Metrics reporting interval in seconds
   UNLEASH_DISABLE_METRICS=false        # Disable metrics reporting
   FEATURE_FLAG_CACHE_TTL=300           # Redis cache TTL in seconds (5 minutes)
   FEATURE_FLAG_KAFKA_TOPIC=feature-flag-events  # Kafka topic for events
   ```

4. **Start Config Service**
   ```bash
   docker-compose up -d config-service
   ```

## Usage

### Creating Flags in Unleash

#### Via Unleash UI

1. Navigate to http://localhost:4242
2. Click "Create feature toggle"
3. Enter flag name (e.g., `new-ui-enabled`)
4. Configure strategies:
   - **Default**: Always enabled/disabled
   - **Gradual rollout**: Percentage-based rollout
   - **User IDs**: Target specific users
   - **Custom**: Custom strategy implementation

#### Via Unleash API

```bash
curl -X POST http://localhost:4242/api/admin/projects/default/features \
  -H 'Authorization: Bearer YOUR_API_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "new-ui-enabled",
    "description": "Enable new UI for users",
    "type": "release"
  }'
```

#### Best Practices for Naming

- Use kebab-case: `new-ui-enabled`, `dark-mode-toggle`
- Be descriptive: `enable-payment-v2` not `payment2`
- Include environment context in description, not name
- Use consistent prefixes for related flags

### Evaluating Flags

#### REST API Examples

**Evaluate Boolean Flag**
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate/boolean \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_name": "new-ui-enabled",
    "user_id": "user-123",
    "context": {"region": "us-west", "subscription_tier": "premium"},
    "default_value": false,
    "environment": "development"
  }'
```

**Evaluate with Variant**
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_name": "theme-variant",
    "user_id": "user-456",
    "default_value": "light",
    "environment": "production"
  }'
```

**Bulk Evaluation**
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate/bulk \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_names": ["new-ui-enabled", "dark-mode", "premium-features"],
    "user_id": "user-789",
    "environment": "development"
  }'
```

#### Python SDK Examples (for other services)

**HTTP Client Pattern**
```python
from examples.feature_flag_client import FeatureFlagClient

client = FeatureFlagClient("http://config-service:8082")
enabled = await client.is_enabled("new-ui-enabled", user_id="user-123")
```

**Direct OpenFeature SDK**
```python
from openfeature import api
from openfeature.evaluation_context import EvaluationContext

client = api.get_client()
ctx = EvaluationContext(targeting_key="user-123", attributes={"region": "us-west"})
enabled = client.get_boolean_value("new-ui-enabled", False, ctx)
```

### Flag Types

#### Boolean Flags
Simple on/off flags for feature toggles.

```python
enabled = await client.is_enabled("new-ui-enabled", user_id="user-123")
```

#### String Variants
Return different string values based on context. Variants are configured in Unleash with payload values.

```python
variant = client.get_string_value("theme-variant", "light", ctx)
# Returns: "light", "dark", or "auto" based on variant configuration
```

**How Variants Work**:
- Variants are configured in Unleash UI with names and optional payloads
- The provider checks if a variant is enabled for the given context
- If enabled, returns the variant name or payload value (if payload contains "value")
- If no variant matches, returns the default value

#### Integer/Float Flags
Numeric values for configuration. Values are stored in variant payloads.

```python
max_retries = client.get_integer_value("max-retries", 3, ctx)
timeout = client.get_float_value("request-timeout", 5.0, ctx)
```

**How Numeric Flags Work**:
- Configure a variant in Unleash with a payload containing `{"value": 5}`
- The provider extracts the numeric value from the variant payload
- If no variant matches or payload is invalid, returns the default value
- Supports type conversion with error handling

#### Object Flags (JSON)
Complex configuration objects. Values are stored as JSON in variant payloads.

```python
config = client.get_object_value("feature-config", {}, ctx)
# Returns: {"enabled": true, "threshold": 0.8, "regions": ["us", "eu"]}
```

**How Object Flags Work**:
- Configure a variant in Unleash with a JSON payload: `{"value": {"enabled": true, "threshold": 0.8}}`
- The provider parses the JSON payload and returns the object
- Supports both string JSON and direct object payloads
- If parsing fails or no variant matches, returns the default value

## Integration Patterns

### For Other Services

#### HTTP API Consumption

Use the FeatureFlagClient from examples:

```python
from examples.feature_flag_client import FeatureFlagClient

class MyService:
    def __init__(self):
        self.flag_client = FeatureFlagClient("http://config-service:8082")
    
    async def process_request(self, user_id: str):
        if await self.flag_client.is_enabled("new-algorithm", user_id=user_id):
            return await self.new_algorithm()
        else:
            return await self.old_algorithm()
```

#### Direct OpenFeature SDK Usage

If your service has OpenFeature SDK configured:

```python
from openfeature import api
from openfeature.evaluation_context import EvaluationContext

def check_feature(flag_name: str, user_id: str, **context):
    client = api.get_client()
    ctx = EvaluationContext(targeting_key=user_id, attributes=context)
    return client.get_boolean_value(flag_name, False, ctx)
```

#### Caching Strategies

- Cache evaluation results in your service (TTL: 5-15 minutes)
- Use consistent user_id for sticky behavior
- Invalidate cache on flag updates (via Kafka events)

### Context Mapping

#### User Targeting

```python
ctx = EvaluationContext(
    targeting_key="user-123",  # Maps to Unleash userId
    attributes={
        "email": "user@example.com",
        "subscription_tier": "premium",
        "region": "us-west"
    }
)
```

#### Custom Properties

All attributes in EvaluationContext are passed to Unleash as context properties and can be used in custom strategies.

**Context Mapping Details**:
- `targeting_key` → Unleash `userId`
- `session_id` (if present) → Unleash `sessionId`
- All `attributes` → Unleash context properties (passed as-is)
- `environment` → Added automatically from provider configuration

**Example Context Flow**:
```python
# OpenFeature EvaluationContext
EvaluationContext(
    targeting_key="user-123",
    attributes={"region": "us-west", "tier": "premium"}
)

# Maps to Unleash Context
{
    "userId": "user-123",
    "region": "us-west",
    "tier": "premium",
    "environment": "development"
}
```

This context can then be used in Unleash strategies for targeting:
- User ID targeting: `userId IN ["user-123", "user-456"]`
- Custom property targeting: `region == "us-west" AND tier == "premium"`
- Gradual rollout: Percentage-based with sticky user assignment

## Operational Guide

### Monitoring

#### Evaluation Metrics

- Total evaluations per flag
- Evaluation success/failure rates
- Cache hit rates
- Average evaluation latency

#### Error Rates

Monitor for:
- Unleash connection failures
- Evaluation errors
- Cache misses

#### Cache Hit Rates

Track Redis cache performance:
- High hit rate (>80%): Good caching
- Low hit rate (<50%): Consider increasing TTL or cache key strategy

### Troubleshooting

#### Unleash Connection Issues

**Symptoms**: Flags always return default values, errors in logs

**Solutions**:
1. Check Unleash server health: `curl http://localhost:4242/health`
2. Verify UNLEASH_URL and UNLEASH_API_TOKEN
3. Check network connectivity between services
4. Review Unleash server logs

#### Cache Invalidation

**Symptoms**: Flag changes not reflected immediately

**Solutions**:
1. Reduce cache TTL (FEATURE_FLAG_CACHE_TTL)
2. Manually invalidate cache keys
3. Use Kafka events to trigger cache invalidation

#### Sync Failures

**Symptoms**: Local flags out of sync with Unleash

**Solutions**:
1. Run manual sync: `POST /api/v1/feature-flags/sync?environment=development`
2. Check Unleash API connectivity
3. Verify API token permissions

### Best Practices

#### Flag Naming Conventions

- Use kebab-case: `new-ui-enabled`
- Be descriptive: `enable-payment-v2` not `payment2`
- Group related flags with prefixes: `ui-dark-mode`, `ui-new-layout`
- Include environment in description, not name

#### Lifecycle Management

1. **Create**: Create flag in Unleash UI
2. **Test**: Test in development environment
3. **Rollout**: Gradually enable in staging, then production
4. **Monitor**: Track evaluation metrics and errors
5. **Cleanup**: Archive or delete unused flags

#### Cleanup Strategies

- Archive flags after 90 days of no evaluations
- Delete flags that are permanently enabled (replace with code)
- Document flag purpose and lifecycle

#### Testing with Flags

```python
# In tests, use default values or mock provider
def test_feature_with_flag():
    # Test with flag enabled
    with mock_flag("new-ui-enabled", True):
        result = process_request()
        assert result.has_new_ui()
    
    # Test with flag disabled
    with mock_flag("new-ui-enabled", False):
        result = process_request()
        assert not result.has_new_ui()
```

## API Reference

### POST /api/v1/feature-flags/evaluate

Evaluate a single feature flag with detailed response.

**Request**:
```json
{
  "flag_name": "new-ui-enabled",
  "user_id": "user-123",
  "context": {"region": "us-west"},
  "default_value": false,
  "environment": "development"
}
```

**Response**:
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "variant": null,
  "reason": "TARGETING_MATCH",
  "evaluated_at": "2024-01-15T10:30:00Z"
}
```

### POST /api/v1/feature-flags/evaluate/boolean

Evaluate boolean flag, returns simple boolean result.

**Request**: Same as above

**Response**:
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "reason": "TARGETING_MATCH"
}
```

### POST /api/v1/feature-flags/evaluate/bulk

Bulk evaluate multiple flags.

**Request**:
```json
{
  "flag_names": ["flag1", "flag2", "flag3"],
  "user_id": "user-123",
  "environment": "development"
}
```

**Response**:
```json
{
  "results": {
    "flag1": {"value": true, "reason": "TARGETING_MATCH"},
    "flag2": {"value": false, "reason": "DEFAULT"},
    "flag3": {"value": true, "reason": "TARGETING_MATCH"}
  }
}
```

### GET /api/v1/feature-flags/{name}

Get feature flag details.

**Query Parameters**:
- `environment` (required): Environment name

**Response**:
```json
{
  "id": 1,
  "name": "new-ui-enabled",
  "description": "Enable new UI",
  "is_enabled": true,
  "environment": "development",
  "evaluation_count": 1234,
  "last_evaluated_at": "2024-01-15T10:30:00Z",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z"
}
```

### GET /api/v1/feature-flags

List feature flags with pagination.

**Query Parameters**:
- `environment` (optional): Filter by environment
- `limit` (optional, default 50, max 100): Number of records per page
- `offset` (optional, default 0): Pagination offset

**Response**:
```json
{
  "items": [
    {
      "id": 1,
      "name": "new-ui-enabled",
      "description": "Enable new UI",
      "is_enabled": true,
      "environment": "development",
      "evaluation_count": 1234,
      "last_evaluated_at": "2024-01-15T10:30:00Z",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 50,
  "limit": 50,
  "offset": 0
}
```

### POST /api/v1/feature-flags

Create a new feature flag in the local database (admin).

**Request**:
```json
{
  "name": "new-feature",
  "description": "New feature description",
  "is_enabled": false,
  "environment": "development",
  "rollout_percentage": "25",
  "target_users": ["user-1", "user-2"]
}
```

**Response**: Same as GET /api/v1/feature-flags/{name}

**Note**: Flags should typically be created in Unleash UI. This endpoint is for local flag management.

### PUT /api/v1/feature-flags/{name}

Update a feature flag (admin).

**Query Parameters**:
- `environment` (required): Environment name

**Request**:
```json
{
  "is_enabled": true,
  "description": "Updated description"
}
```

**Response**: Same as GET /api/v1/feature-flags/{name}

**Note**: Only provided fields will be updated. Cache is automatically invalidated.

### DELETE /api/v1/feature-flags/{name}

Delete a feature flag (admin).

**Query Parameters**:
- `environment` (required): Environment name

**Response**: 204 No Content

**Note**: Cache is automatically invalidated. Evaluation history is preserved.

### POST /api/v1/feature-flags/sync

Sync flags from Unleash to local database (admin).

**Query Parameters**:
- `environment` (required): Environment name

**Response**:
```json
{
  "synced_count": 15,
  "environment": "development"
}
```

**How Sync Works**:
1. Fetches all flags from Unleash Admin API
2. For each flag, determines if it's enabled based on strategies and environment
3. Upserts flag into local database
4. Updates `last_synced_at` timestamp
5. Returns count of synced flags

**Note**: This is a manual sync operation. Flags are evaluated in real-time from Unleash, but this sync populates the local cache for faster lookups and audit trails.

### GET /api/v1/feature-flags/{name}/history

Get evaluation history for a flag.

**Query Parameters**:
- `environment` (required): Environment name
- `limit` (optional, default 100, max 1000): Number of records

**Response**:
```json
[
  {
    "id": 1,
    "flag_name": "new-ui-enabled",
    "user_id": "user-123",
    "context": {"region": "us-west"},
    "result": true,
    "variant": null,
    "evaluated_value": null,
    "environment": "development",
    "evaluated_at": "2024-01-15T10:30:00Z",
    "evaluation_reason": "TARGETING_MATCH"
  }
]
```

**Note**: 
- `result` is populated for boolean flags
- `evaluated_value` is populated for non-boolean flags (string, int, float, object)
- `variant` is populated when a variant is returned

## Implementation Details

### Evaluation Flow

1. **Request Received**: API receives evaluation request with flag name, user_id, context, and default value
2. **Cache Check**: Check Redis cache using key: `feature_flag:eval:{environment}:{flag_name}:{user_id}:{context_hash}`
3. **Cache Hit**: If found, return cached result immediately
4. **Cache Miss**: 
   - Build OpenFeature EvaluationContext from user_id and context
   - Call OpenFeature client with appropriate method based on default_value type
   - Provider maps context to Unleash format and calls Unleash SDK
   - Unleash evaluates flag based on strategies and returns result
5. **Record Evaluation**: Store evaluation in database audit trail
6. **Cache Result**: Store result in Redis with TTL
7. **Publish Event**: Send Kafka event for analytics
8. **Return Response**: Return evaluation result to client

### Error Handling

The system implements graceful degradation:

- **Unleash Connection Failure**: Returns default value with reason "ERROR"
- **Provider Not Initialized**: Returns default value with reason "ERROR"
- **Invalid Flag Name**: Returns default value with reason "DEFAULT"
- **Evaluation Exception**: Catches exceptions, logs error, returns default value
- **Cache Errors**: Logs warning but continues with evaluation
- **Database Errors**: Logs warning but doesn't fail the request

### Cache Key Generation

Cache keys include context hash for consistent caching:

```python
# Context: {"region": "us-west", "tier": "premium"}
# Hash: SHA256 of sorted JSON → first 16 chars
# Key: feature_flag:eval:development:new-ui-enabled:user-123:a1b2c3d4e5f6g7h8
```

This ensures:
- Same context → same cache key → same result
- Different context → different cache key → correct evaluation
- Context changes invalidate cache naturally (new hash)

### Database Schema

**feature_flags table**:
- `id`: Primary key
- `name`: Flag identifier (unique with environment)
- `description`: Human-readable description
- `is_enabled`: Boolean status
- `rollout_percentage`: Percentage string (e.g., "25")
- `target_users`: JSON array of user IDs
- `environment`: Environment name (development/staging/production)
- `unleash_flag_name`: Original name in Unleash
- `last_synced_at`: Last sync timestamp
- `evaluation_count`: Total number of evaluations
- `last_evaluated_at`: Most recent evaluation timestamp
- `created_at`, `updated_at`: Timestamps

**feature_flag_evaluations table**:
- `id`: Primary key
- `flag_name`: Flag identifier
- `user_id`: User identifier (nullable)
- `context`: JSON object with evaluation context
- `result`: Boolean result (for boolean flags)
- `variant`: Variant name (if applicable)
- `evaluated_value`: JSON value (for non-boolean flags)
- `environment`: Environment name
- `evaluated_at`: Evaluation timestamp
- `evaluation_reason`: Reason (TARGETING_MATCH, DEFAULT, ERROR)

### Kafka Event Structure

**FEATURE_FLAG_EVALUATED**:
```json
{
  "event_type": "FEATURE_FLAG_EVALUATED",
  "flag_name": "new-ui-enabled",
  "user_id": "user-123",
  "environment": "development",
  "value": "true",
  "reason": "TARGETING_MATCH"
}
```

**FEATURE_FLAG_CREATED**:
```json
{
  "event_type": "FEATURE_FLAG_CREATED",
  "flag_name": "new-feature",
  "environment": "development"
}
```

**FEATURE_FLAG_UPDATED**:
```json
{
  "event_type": "FEATURE_FLAG_UPDATED",
  "flag_name": "new-feature",
  "environment": "development"
}
```

**FEATURE_FLAG_DELETED**:
```json
{
  "event_type": "FEATURE_FLAG_DELETED",
  "flag_name": "old-feature",
  "environment": "development"
}
```

### Provider Initialization

The Unleash provider is initialized at application startup:

1. Reads environment variables for configuration
2. Creates `UnleashFeatureProvider` instance
3. Initializes Unleash client with refresh and metrics intervals
4. Registers provider with OpenFeature API
5. Stores client in FastAPI app state for dependency injection

**Initialization Parameters**:
- `refresh_interval`: How often to fetch flag updates from Unleash (default: 15s)
- `metrics_interval`: How often to report metrics to Unleash (default: 60s)
- `disable_metrics`: Whether to disable metrics reporting (default: false)
- `environment`: Which Unleash environment to use (development/staging/production)

## Examples

### Simple Boolean Flag

```python
# Check if feature is enabled
if await client.is_enabled("new-ui-enabled", user_id="user-123"):
    render_new_ui()
else:
    render_old_ui()
```

### Gradual Rollout

```python
# Flag configured for 25% rollout in Unleash
enabled = await client.is_enabled("new-algorithm", user_id="user-123")
# Consistent user_id ensures sticky behavior
```

### User Targeting

```python
# Flag enabled only for premium users
enabled = await client.is_enabled(
    "premium-features",
    user_id="user-456",
    context={"subscription_tier": "premium"}
)
```

### A/B Testing

```python
# Get variant for A/B test
variant = client.get_string_value("ab-test-variant", "control", ctx)
if variant == "variant-a":
    show_variant_a()
elif variant == "variant-b":
    show_variant_b()
else:
    show_control()
```

### Kill Switch

```python
# Emergency kill switch
if await client.is_enabled("payment-processing", user_id="user-789"):
    process_payment()
else:
    return_error("Payment processing temporarily disabled")
```

### Configuration Flags (Numeric/Object)

```python
# Get max retry count from flag
max_retries = await client.evaluate_flag(
    flag_name="api-max-retries",
    user_id="user-123",
    default_value=3,
    environment="production"
)
# Returns integer value from variant payload

# Get complex configuration object
config = await client.evaluate_flag(
    flag_name="feature-config",
    user_id="user-123",
    default_value={"enabled": False, "threshold": 0.5},
    environment="production"
)
# Returns object from variant payload JSON
```

### Bulk Evaluation for Performance

```python
# Evaluate multiple flags in one request
results = await client.bulk_evaluate_flags(
    flag_names=["ui-new-layout", "dark-mode", "premium-features"],
    user_id="user-123",
    context={"tier": "premium"},
    environment="production"
)
# Returns: {"ui-new-layout": {"value": true, "reason": "TARGETING_MATCH"}, ...}
```

### Error Handling Pattern

```python
try:
    enabled = await client.is_enabled("new-feature", user_id="user-123")
    if enabled:
        use_new_feature()
    else:
        use_old_feature()
except Exception as e:
    # Graceful fallback - use default behavior
    logger.error(f"Feature flag evaluation failed: {e}")
    use_old_feature()  # Safe default
```

### Cache-Aware Evaluation

```python
# For high-frequency evaluations, consider caching in your service
from functools import lru_cache
from datetime import datetime, timedelta

class CachedFlagClient:
    def __init__(self, client, ttl_minutes=5):
        self.client = client
        self.cache = {}
        self.ttl = timedelta(minutes=ttl_minutes)
    
    async def is_enabled(self, flag_name, user_id, **kwargs):
        cache_key = f"{flag_name}:{user_id}"
        if cache_key in self.cache:
            value, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < self.ttl:
                return value
        
        value = await self.client.is_enabled(flag_name, user_id, **kwargs)
        self.cache[cache_key] = (value, datetime.now())
        return value
```

## Advanced Topics

### Custom Strategies in Unleash

Unleash supports custom strategies that can use any context property:

1. **User ID Strategy**: Target specific users
   ```json
   {
     "name": "userWithId",
     "parameters": {
       "userIds": "user-123,user-456,user-789"
     }
   }
   ```

2. **Gradual Rollout**: Percentage-based with sticky assignment
   ```json
   {
     "name": "gradualRollout",
     "parameters": {
       "percentage": 25,
       "groupId": "new-feature"
     }
   }
   ```

3. **Custom Property Strategy**: Use any context attribute
   ```json
   {
     "name": "customProperty",
     "parameters": {
       "property": "subscription_tier",
       "values": "premium,gold"
     }
   }
   ```

### Monitoring and Observability

**Key Metrics to Monitor**:
- Evaluation latency (p50, p95, p99)
- Cache hit rate (target: >80%)
- Error rate (target: <1%)
- Evaluation count per flag
- Flag usage distribution

**Logging**:
- All evaluation errors are logged with full context
- Cache operations are logged at debug level
- Sync operations are logged with counts
- Kafka publish failures are logged as warnings

**Health Checks**:
- Unleash connection status
- Redis connectivity
- Database connectivity
- Kafka producer status

### Performance Considerations

1. **Cache TTL**: Balance between freshness and performance
   - High TTL (10-15 min): Better performance, slower updates
   - Low TTL (1-2 min): Faster updates, more database load

2. **Bulk Evaluation**: Use for multiple flags to reduce HTTP overhead

3. **Connection Pooling**: HTTP client should use connection pooling

4. **Async Operations**: All operations are async for better concurrency

5. **Database Indexing**: Ensure indexes on `flag_name`, `environment`, `user_id` in evaluations table

