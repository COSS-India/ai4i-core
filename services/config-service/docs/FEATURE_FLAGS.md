# Feature Flags with Unleash and OpenFeature

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

3. **Custom Unleash Provider**
   - Wraps Unleash Python SDK
   - Implements OpenFeature provider interface
   - Handles context mapping and error handling

4. **Local Database (config_db)**
   - `feature_flags`: Cached flag definitions
   - `feature_flag_evaluations`: Audit trail of all evaluations

5. **Redis Cache**
   - Evaluation result caching (TTL: 300s)
   - Reduces database load

6. **Kafka Events**
   - Flag creation/update/deletion events
   - Evaluation events for analytics

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
   ```bash
   UNLEASH_URL=http://unleash:4242/api
   UNLEASH_APP_NAME=config-service
   UNLEASH_INSTANCE_ID=config-service-1
   UNLEASH_API_TOKEN=your-api-token-here
   UNLEASH_ENVIRONMENT=development
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
Return different string values based on context.

```python
variant = client.get_string_value("theme-variant", "light", ctx)
# Returns: "light", "dark", or "auto"
```

#### Integer/Float Flags
Numeric values for configuration.

```python
max_retries = client.get_integer_value("max-retries", 3, ctx)
timeout = client.get_float_value("request-timeout", 5.0, ctx)
```

#### Object Flags (JSON)
Complex configuration objects.

```python
config = client.get_object_value("feature-config", {}, ctx)
# Returns: {"enabled": true, "threshold": 0.8, "regions": ["us", "eu"]}
```

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

### GET /api/v1/feature-flags/{name}/history

Get evaluation history for a flag.

**Query Parameters**:
- `environment` (required): Environment name
- `limit` (optional, default 100): Number of records

**Response**:
```json
[
  {
    "id": 1,
    "flag_name": "new-ui-enabled",
    "user_id": "user-123",
    "result": true,
    "evaluated_at": "2024-01-15T10:30:00Z",
    "evaluation_reason": "TARGETING_MATCH"
  }
]
```

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

