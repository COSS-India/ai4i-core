# Feature Flags with Unleash and OpenFeature

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
  - [Data Flow](#data-flow)
  - [Redis Caching Strategy](#redis-caching-strategy)
  - [Components](#components)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Configuration](#configuration)
- [Usage](#usage)
  - [Creating Flags in Unleash](#creating-flags-in-unleash)
  - [Evaluating Flags](#evaluating-flags)
  - [Listing Flags](#listing-flags)
- [API Reference](#api-reference)
- [Data Flow Details](#data-flow-details)
- [Redis Cache Structure](#redis-cache-structure)
- [Troubleshooting](#troubleshooting)

## Overview

The feature flag system uses a **Redis and Unleash only** architecture:

- **Unleash Server**: Source of truth for all feature flags
- **OpenFeature SDK**: Vendor-neutral abstraction for flag evaluation
- **Redis**: High-performance caching layer
- **Kafka**: Event publishing for flag evaluations

**No PostgreSQL dependencies** - All flag metadata is fetched from Unleash and cached in Redis.

## Architecture

### Components

1. **Unleash Server** (Port 4242)
   - Flag definitions and strategies
   - Web UI for flag management
   - REST Admin API for flag operations
   - Client API for SDK evaluation

2. **OpenFeature SDK**
   - Vendor-neutral evaluation API
   - Supports multiple providers via domains
   - Consistent interface across services

3. **Custom Unleash Provider** (`providers/unleash_provider.py`)
   - Bridges Unleash Python SDK and OpenFeature
   - Handles context mapping
   - Manages client lifecycle

4. **Feature Flag Service** (`services/feature_flag_service.py`)
   - Fetches flags from Unleash Admin API
   - Caches flag metadata in Redis
   - Evaluates flags via OpenFeature SDK
   - Publishes events to Kafka

5. **Redis Cache**
   - Evaluation results cache (TTL: 5 minutes)
   - Flag metadata cache (TTL: 5 minutes)
   - Flag list cache (TTL: 5 minutes)

### Data Flow

#### Flag Evaluation Flow

```
┌─────────────┐
│   Client    │
│  Request    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Feature Flag Service               │
│  (evaluate_flag)                    │
└──────┬──────────────────────────────┘
       │
       ├─► Check Redis Cache
       │   └─► Cache Hit? Return cached result
       │
       └─► Cache Miss
           │
           ├─► OpenFeature SDK ──► Unleash Client API
           │   └─► Returns evaluation result
           │
           ├─► Cache result in Redis (TTL: 5 min)
           │
           └─► Publish event to Kafka
               └─► Return result to client
```

#### Flag Listing Flow

```
┌─────────────┐
│   Client    │
│  GET /flags │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Feature Flag Service               │
│  (get_feature_flags)                │
└──────┬──────────────────────────────┘
       │
       ├─► Check Redis Cache
       │   └─► Cache Hit? Return cached list
       │
       └─► Cache Miss
           │
           ├─► Unleash Admin API
           │   └─► GET /api/admin/projects/default/features
           │       └─► Returns feature list
           │
           ├─► Convert Unleash format to API format
           │
           ├─► Cache in Redis (TTL: 5 min)
           │
           └─► Return paginated results
```

#### Sync Flow

```
┌─────────────┐
│   Client    │
│  POST /sync │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Feature Flag Service               │
│  (sync_flags_from_unleash)          │
└──────┬──────────────────────────────┘
       │
       ├─► Invalidate Redis cache
       │
       ├─► Fetch from Unleash Admin API
       │   └─► GET /api/admin/projects/default/features
       │
       ├─► Convert and cache in Redis
       │
       └─► Return sync count
```

### Redis Caching Strategy

#### Cache Keys

1. **Evaluation Results**
   ```
   feature_flag:eval:{environment}:{flag_name}:{user_id}:{context_hash}
   ```
   - Stores: Evaluation result (value, variant, reason)
   - TTL: 5 minutes (configurable via `FEATURE_FLAG_CACHE_TTL`)
   - Purpose: Avoid re-evaluating same flag for same context

2. **Flag Metadata**
   ```
   feature_flag:metadata:{environment}:{flag_name}
   ```
   - Stores: Full flag details (name, description, enabled state, etc.)
   - TTL: 5 minutes
   - Purpose: Fast lookup of individual flag details

3. **Flag List**
   ```
   feature_flags:list:{environment}
   ```
   - Stores: Complete list of flags for an environment
   - TTL: 5 minutes
   - Purpose: Fast listing without API calls

#### Cache Invalidation

- **On Sync**: All caches for an environment are invalidated
- **On Flag Update**: Individual flag caches are invalidated (if updated via Unleash UI)
- **Automatic**: Cache expires after TTL (5 minutes)

#### Cache Benefits

- **Performance**: Reduces Unleash API calls by ~95%
- **Resilience**: Cached results available if Unleash is temporarily unavailable
- **Cost**: Reduces load on Unleash server

## Setup

### Prerequisites

1. **Unleash Server Running**
   - Default: http://unleash:4242
   - Access UI: http://localhost:4242
   - Default credentials: admin/unleash4all

2. **Redis Running**
   - Default: redis:6379
   - Used for caching

3. **Kafka Running** (optional)
   - Default: kafka:9092
   - Used for event publishing

### Configuration

#### Required Environment Variables

```bash
# Unleash Configuration
UNLEASH_URL=http://unleash:4242/api
UNLEASH_APP_NAME=config-service
UNLEASH_INSTANCE_ID=config-service-1
UNLEASH_API_TOKEN=your-admin-token-here  # Must be Admin token, not Client token
UNLEASH_ENVIRONMENT=development
```

**Understanding UNLEASH_ENVIRONMENT (OPTIONAL)**

The `UNLEASH_ENVIRONMENT` variable is **OPTIONAL** and only affects the Unleash SDK client initialization:

- **If SET**: SDK client is initialized for this environment (can be used as fallback for complex targeting)
- **If NOT SET**: SDK is disabled. Evaluation uses Admin API only, which works correctly for **ALL environments**

**How It Works:**
- The evaluation system uses the **Admin API** to fetch flag configuration for the requested environment
- This ensures **enabled/disabled state is always correct** for any environment
- For targeting evaluation (percentage rollouts, user targeting), the system:
  1. Uses Admin API data to evaluate basic targeting (user lists, percentage rollouts)
  2. Falls back to SDK if available and needed for complex strategies
  3. Works correctly even when SDK environment doesn't match requested environment

**Recommendations:**
1. **Leave `UNLEASH_ENVIRONMENT` UNSET** (recommended) - Works correctly for all environments
2. **Set it only if** you need SDK-based evaluation for complex targeting in a specific environment
3. **For multi-environment deployments**: Leave it unset to support all environments correctly

**Example:**
```bash
# Recommended: Leave unset (commented out) for multi-environment support
# UNLEASH_ENVIRONMENT=development

# Optional: Set only if you need SDK for complex targeting
# UNLEASH_ENVIRONMENT=production

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your-redis-password

# Optional Configuration
FEATURE_FLAG_CACHE_TTL=300              # Cache TTL in seconds (default: 5 minutes)
FEATURE_FLAG_KAFKA_TOPIC=feature-flag-events
UNLEASH_AUTO_SYNC_ON_STARTUP=false      # Auto-sync on service startup
```

#### Creating Admin Token in Unleash

1. Navigate to Unleash UI: http://localhost:4242
2. Go to **Settings → API Access**
3. Click **Create API token**
4. Select token type: **Admin** (required for Admin API)
5. Copy the token and set `UNLEASH_API_TOKEN`

**Important**: The Admin API requires an **Admin token**, not a Client token. Client tokens are only for SDK evaluation.

## Usage

### Creating Flags in Unleash

#### Via Unleash UI

1. Navigate to http://localhost:4242
2. Click **"Create feature toggle"**
3. Enter flag name (e.g., `new-ui-enabled`)
4. Configure environment settings:
   - Enable/disable for each environment
   - Add strategies (gradual rollout, user targeting, etc.)
5. Save the flag

#### Via Unleash Admin API

```bash
curl -X POST http://localhost:4242/api/admin/projects/default/features \
  -H 'Authorization: Bearer YOUR_ADMIN_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "new-ui-enabled",
    "description": "Enable new UI for users",
    "type": "release"
  }'
```

### Evaluating Flags

#### What is Flag Evaluation?

**Flag evaluation** is the process of determining whether a feature flag is enabled or what value it should return for a specific user and context. The evaluation considers:

- Flag configuration in Unleash (enabled/disabled state)
- Targeting strategies (user IDs, percentages, constraints)
- User context (user ID, region, custom attributes)
- Environment settings

The evaluation returns:
- **Value**: The actual flag value (true/false, string, number, or object)
- **Reason**: Why this value was returned (TARGETING_MATCH, DEFAULT, ERROR)
- **Variant**: If applicable, which variant was selected

#### Evaluation Endpoints

There are three evaluation endpoints for different use cases:

1. **`POST /evaluate`** - Detailed evaluation with full response
2. **`POST /evaluate/boolean`** - Simple boolean evaluation
3. **`POST /evaluate/bulk`** - Evaluate multiple flags at once

#### Request Parameters Explained

All evaluation endpoints use similar request parameters:

```json
{
  "flag_name": "new-ui-enabled",        // Required: Name of the flag to evaluate
  "user_id": "user-123",                 // Optional: User identifier for targeting
  "context": {                           // Optional: Additional context attributes
    "region": "us-west",
    "plan": "premium",
    "beta": true
  },
  "default_value": false,                // Required: Fallback value if evaluation fails
  "environment": "development"           // Required: Environment name
}
```

**Parameter Details:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `flag_name` | string | ✅ Yes | The name of the feature flag to evaluate. Must match the flag name in Unleash. |
| `default_value` | bool/str/int/float/dict | ✅ Yes | The value to return if the flag evaluation fails or the flag doesn't exist. Also determines the flag type (boolean, string, integer, float, or object). |
| `environment` | string | ✅ Yes | The environment name (development, staging, or production). Must match the environment in Unleash. |
| `user_id` | string | ❌ No | User identifier for user-based targeting. Used by strategies like "userWithId" to target specific users. |
| `context` | object | ❌ No | Additional context attributes for advanced targeting. Can include any key-value pairs that strategies might use (e.g., region, plan, beta status). |

**How Context is Used:**

The `context` object allows you to pass custom attributes that Unleash strategies can use for targeting:

- **User targeting**: `{"userId": "user-123"}`
- **Region-based**: `{"region": "us-west"}`
- **Plan-based**: `{"plan": "premium"}`
- **Custom attributes**: `{"beta": true, "department": "engineering"}`

Strategies in Unleash can use these context attributes to determine if a flag should be enabled for a specific request.

#### REST API Examples

**1. Evaluate Boolean Flag (Simple)**
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate/boolean \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_name": "new-ui-enabled",
    "user_id": "user-123",
    "context": {"region": "us-west"},
    "default_value": false,
    "environment": "development"
  }'
```

**Response:**
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "reason": "TARGETING_MATCH"
}
```

**2. Evaluate with Detailed Response**
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_name": "new-ui-enabled",
    "user_id": "user-123",
    "context": {"region": "us-west"},
    "default_value": false,
    "environment": "development"
  }'
```

**Response:**
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "variant": null,
  "reason": "TARGETING_MATCH",
  "evaluated_at": "2024-01-15T10:30:00Z"
}
```

**3. Evaluate String Flag (Variant)**
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_name": "theme-color",
    "user_id": "user-123",
    "context": {},
    "default_value": "blue",
    "environment": "development"
  }'
```

**Response:**
```json
{
  "flag_name": "theme-color",
  "value": "red",
  "variant": "red",
  "reason": "TARGETING_MATCH",
  "evaluated_at": "2024-01-15T10:30:00Z"
}
```

**4. Bulk Evaluate Multiple Flags**
```bash
curl -X POST http://localhost:8082/api/v1/feature-flags/evaluate/bulk \
  -H 'Content-Type: application/json' \
  -d '{
    "flag_names": ["new-ui-enabled", "dark-mode", "beta-features"],
    "user_id": "user-123",
    "context": {"region": "us-west", "plan": "premium"},
    "environment": "development"
  }'
```

**Response:**
```json
{
  "results": {
    "new-ui-enabled": {
      "flag_name": "new-ui-enabled",
      "value": true,
      "variant": null,
      "reason": "TARGETING_MATCH",
      "evaluated_at": "2024-01-15T10:30:00Z"
    },
    "dark-mode": {
      "flag_name": "dark-mode",
      "value": false,
      "variant": null,
      "reason": "DEFAULT",
      "evaluated_at": "2024-01-15T10:30:00Z"
    },
    "beta-features": {
      "flag_name": "beta-features",
      "value": true,
      "variant": null,
      "reason": "TARGETING_MATCH",
      "evaluated_at": "2024-01-15T10:30:00Z"
    }
  }
}
```

#### Evaluation Reasons

The `reason` field indicates why a particular value was returned:

- **`TARGETING_MATCH`**: Flag is enabled and matches targeting rules (user ID, percentage, constraints)
- **`DEFAULT`**: Flag is disabled or doesn't match targeting rules, returns default value
- **`ERROR`**: Evaluation failed (flag doesn't exist, Unleash unavailable, etc.), returns default value

#### Use Cases

**1. Feature Rollout**
```json
{
  "flag_name": "new-checkout-flow",
  "user_id": "user-123",
  "context": {"region": "us-east"},
  "default_value": false,
  "environment": "production"
}
```
Use case: Gradually roll out a new feature to specific users or regions.

**2. A/B Testing**
```json
{
  "flag_name": "checkout-button-color",
  "user_id": "user-456",
  "context": {},
  "default_value": "blue",
  "environment": "production"
}
```
Use case: Test different variants (colors, layouts) with different user segments.

**3. User Targeting**
```json
{
  "flag_name": "premium-features",
  "user_id": "user-789",
  "context": {"plan": "premium", "subscription_active": true},
  "default_value": false,
  "environment": "production"
}
```
Use case: Enable features for specific user segments (premium users, beta testers).

**4. Environment-Specific Features**
```json
{
  "flag_name": "debug-logging",
  "user_id": null,
  "context": {},
  "default_value": false,
  "environment": "development"
}
```
Use case: Enable features only in specific environments (dev, staging, production).

### Listing Flags

**List All Flags**
```bash
curl "http://localhost:8082/api/v1/feature-flags?environment=development&limit=50&offset=0"
```

**Get Single Flag**
```bash
curl "http://localhost:8082/api/v1/feature-flags/test-flag-2?environment=development"
```

**Sync/Refresh Cache**
```bash
curl -X POST "http://localhost:8082/api/v1/feature-flags/sync?environment=development"
```

## API Reference

### POST /api/v1/feature-flags/evaluate

Evaluate a feature flag with detailed response. Supports boolean, string, integer, float, and object (dict) flag types.

**Request Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `flag_name` | string | ✅ Yes | Name of the feature flag to evaluate |
| `default_value` | bool/str/int/float/dict | ✅ Yes | Fallback value if evaluation fails. Also determines flag type. |
| `environment` | string | ✅ Yes | Environment name (development/staging/production) |
| `user_id` | string | ❌ No | User identifier for user-based targeting |
| `context` | object | ❌ No | Additional context attributes for targeting (e.g., region, plan, custom attributes) |

**Request Example:**
```json
{
  "flag_name": "new-ui-enabled",
  "user_id": "user-123",
  "context": {"region": "us-west", "plan": "premium"},
  "default_value": false,
  "environment": "development"
}
```

**Response:**
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "variant": null,
  "reason": "TARGETING_MATCH",
  "evaluated_at": "2024-01-15T10:30:00Z"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `flag_name` | string | Name of the evaluated flag |
| `value` | bool/str/int/float/dict | The evaluated flag value |
| `variant` | string/null | Variant name if applicable (for string/object flags) |
| `reason` | string | Evaluation reason: TARGETING_MATCH, DEFAULT, or ERROR |
| `evaluated_at` | string | ISO timestamp of evaluation |

**Flag Types:**

The `default_value` parameter determines the flag type:

- **Boolean**: `"default_value": false` → Returns true/false
- **String**: `"default_value": "blue"` → Returns string value or variant name
- **Integer**: `"default_value": 0` → Returns integer value
- **Float**: `"default_value": 0.0` → Returns float value
- **Object**: `"default_value": {}` → Returns JSON object/dict

### POST /api/v1/feature-flags/evaluate/boolean

Evaluate a boolean feature flag. Returns a simple boolean result without detailed metadata.

**Request Parameters:** Same as `/evaluate` endpoint, but `default_value` must be a boolean.

**Request Example:**
```json
{
  "flag_name": "new-ui-enabled",
  "user_id": "user-123",
  "context": {"region": "us-west"},
  "default_value": false,
  "environment": "development"
}
```

**Response:**
```json
{
  "flag_name": "new-ui-enabled",
  "value": true,
  "reason": "TARGETING_MATCH"
}
```

**Use Case:** When you only need a simple true/false result and don't need evaluation metadata.

### POST /api/v1/feature-flags/evaluate/bulk

Evaluate multiple feature flags in a single request. All flags are evaluated in parallel for better performance.

**Request Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `flag_names` | array[string] | ✅ Yes | List of flag names to evaluate (minimum 1) |
| `environment` | string | ✅ Yes | Environment name (development/staging/production) |
| `user_id` | string | ❌ No | User identifier for user-based targeting |
| `context` | object | ❌ No | Additional context attributes for targeting |

**Request Example:**
```json
{
  "flag_names": ["new-ui-enabled", "dark-mode", "beta-features"],
  "user_id": "user-123",
  "context": {"region": "us-west", "plan": "premium"},
  "environment": "development"
}
```

**Response:**
```json
{
  "results": {
    "new-ui-enabled": {
      "flag_name": "new-ui-enabled",
      "value": true,
      "variant": null,
      "reason": "TARGETING_MATCH",
      "evaluated_at": "2024-01-15T10:30:00Z"
    },
    "dark-mode": {
      "flag_name": "dark-mode",
      "value": false,
      "variant": null,
      "reason": "DEFAULT",
      "evaluated_at": "2024-01-15T10:30:00Z"
    },
    "beta-features": {
      "flag_name": "beta-features",
      "value": true,
      "variant": null,
      "reason": "TARGETING_MATCH",
      "evaluated_at": "2024-01-15T10:30:00Z"
    }
  }
}
```

**Use Case:** When you need to evaluate multiple flags for a single user/context. More efficient than making multiple separate requests.

### GET /api/v1/feature-flags/{name}

Get feature flag details.

**Query Parameters**:
- `environment` (required): Environment name

**Response**:
```json
{
  "name": "new-ui-enabled",
  "description": "Enable new UI",
  "is_enabled": true,
  "environment": "development",
  "unleash_flag_name": "new-ui-enabled",
  "last_synced_at": "2024-01-15T10:30:00Z",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z"
}
```

**Note**: Only fields with actual values are included. Fields like `rollout_percentage` and `target_users` are only included if available from Unleash strategies (may not be in list endpoint response).

### GET /api/v1/feature-flags

List feature flags with pagination.

**Query Parameters**:
- `environment` (required): Environment name
- `limit` (optional, default 50, max 100): Number of records per page
- `offset` (optional, default 0): Pagination offset

**Response**:
```json
{
  "items": [
    {
      "name": "new-ui-enabled",
      "description": "Enable new UI",
      "is_enabled": true,
      "environment": "development",
      "unleash_flag_name": "new-ui-enabled",
      "last_synced_at": "2024-01-15T10:30:00Z",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

**Note**: 
- Only fields with actual values are included (null fields are excluded)
- `rollout_percentage` and `target_users` are only included if available from Unleash strategies
- The list endpoint may not include full strategy details, so these fields may be absent

### POST /api/v1/feature-flags/sync

Refresh feature flags cache from Unleash.

**Query Parameters**:
- `environment` (required): Environment name

**Response**:
```json
{
  "synced_count": 5,
  "environment": "development"
}
```

**How Sync Works**:
1. Invalidates Redis cache for the environment
2. Fetches all flags from Unleash Admin API
3. Converts Unleash format to API response format
4. Caches results in Redis
5. Returns count of synced flags

## Data Flow Details

### Evaluation Request Flow

1. **Client Request** → Feature Flag Service
2. **Check Redis Cache** → Look for cached evaluation result
   - Cache key: `feature_flag:eval:{env}:{flag}:{user}:{context_hash}`
   - If found: Return cached result (fast path)
3. **Cache Miss** → Evaluate via OpenFeature SDK
   - OpenFeature → Unleash Client API
   - Unleash returns evaluation result
4. **Cache Result** → Store in Redis with TTL
5. **Publish Event** → Send to Kafka (optional)
6. **Return Result** → To client

### List Request Flow

1. **Client Request** → Feature Flag Service
2. **Check Redis Cache** → Look for cached flag list
   - Cache key: `feature_flags:list:{environment}`
   - If found: Return cached list (fast path)
3. **Cache Miss** → Fetch from Unleash Admin API
   - GET `/api/admin/projects/default/features`
   - Paginate through all flags
4. **Convert Format** → Unleash format → API response format
5. **Cache Results** → Store in Redis with TTL
6. **Apply Pagination** → Return requested page

### Sync Request Flow

1. **Client Request** → Feature Flag Service
2. **Invalidate Cache** → Delete all cache keys for environment
3. **Fetch from Unleash** → GET `/api/admin/projects/default/features`
4. **Convert & Cache** → Store all flags in Redis
5. **Return Count** → Number of flags synced

## Redis Cache Structure

### Evaluation Cache

```redis
Key: feature_flag:eval:development:new-ui-enabled:user-123:a1b2c3d4
Value: {
  "flag_name": "new-ui-enabled",
  "value": true,
  "variant": null,
  "reason": "TARGETING_MATCH",
  "evaluated_at": "2024-01-15T10:30:00Z"
}
TTL: 300 seconds (5 minutes)
```

### Flag Metadata Cache

```redis
Key: feature_flag:metadata:development:new-ui-enabled
Value: {
  "id": 123456789,
  "name": "new-ui-enabled",
  "description": "Enable new UI",
  "is_enabled": true,
  ...
}
TTL: 300 seconds (5 minutes)
```

### Flag List Cache

```redis
Key: feature_flags:list:development
Value: {
  "flags": [
    {"id": 123456789, "name": "flag1", ...},
    {"id": 987654321, "name": "flag2", ...}
  ],
  "total": 2
}
TTL: 300 seconds (5 minutes)
```

## Troubleshooting

### Issue: Flags not appearing after creating in Unleash UI

**Solution**: Call the sync endpoint to refresh cache:
```bash
curl -X POST "http://localhost:8082/api/v1/feature-flags/sync?environment=development"
```

### Issue: 403 Forbidden - Invalid token

**Cause**: Using Client token instead of Admin token

**Solution**: 
1. Create an Admin token in Unleash UI (Settings → API Access)
2. Update `UNLEASH_API_TOKEN` environment variable
3. Restart the service

### Issue: Empty flag list

**Possible Causes**:
1. Environment name mismatch - Check `UNLEASH_ENVIRONMENT` matches Unleash UI
2. No flags configured for that environment in Unleash
3. Cache issue - Call sync endpoint to refresh

**Debug Steps**:
1. Check logs for API response structure
2. Verify environment name in Unleash UI
3. Call sync endpoint and check logs

### Issue: Stale flag values

**Cause**: Cache TTL too long or cache not invalidated

**Solution**:
1. Call sync endpoint to refresh cache
2. Reduce `FEATURE_FLAG_CACHE_TTL` if needed
3. Check if Unleash flag was actually updated

### Performance Optimization

- **Cache TTL**: Adjust `FEATURE_FLAG_CACHE_TTL` based on needs
  - Lower TTL = More fresh data, more API calls
  - Higher TTL = Less API calls, potentially stale data
- **Redis Memory**: Monitor Redis memory usage
- **Kafka Events**: Disable if not needed (set `FEATURE_FLAG_KAFKA_TOPIC` to empty)

## Best Practices

1. **Always use Admin tokens** for Admin API operations
2. **Call sync endpoint** after creating/updating flags in Unleash UI
3. **Monitor cache hit rates** to optimize TTL
4. **Use appropriate cache TTL** based on update frequency
5. **Handle cache misses gracefully** - fallback to Unleash API
6. **Use bulk evaluation** when evaluating multiple flags
7. **Include user context** for better targeting

## Limitations

1. **Strategy Details**: The list endpoint doesn't include full strategy details (rollout_percentage, target_users may be null)
2. **Evaluation History**: Not tracked (Redis-only mode)
3. **Local Flags**: Not supported - all flags must come from Unleash
4. **Cache Consistency**: Cache may be stale for up to TTL duration (default: 5 minutes)
