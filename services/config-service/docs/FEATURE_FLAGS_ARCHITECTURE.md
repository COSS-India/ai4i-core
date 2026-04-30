# Feature Flags Architecture - Redis & Unleash Only

## System Status: ✅ Working

The feature flag system is fully operational with the Redis + Unleash only architecture.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Feature Flag System                        │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌──────────────┐    ┌──────────────┐
│   Unleash     │    │    Redis     │    │   OpenFeature│
│   Server      │    │    Cache     │    │     SDK      │
└───────────────┘    └──────────────┘    └──────────────┘
        │                     │                     │
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Config Service   │
                    │  Feature Flag API │
                    └───────────────────┘
```

## Data Flow

### 1. Flag Evaluation Flow

```
Client Request
    │
    ▼
┌─────────────────────────────────────┐
│  Feature Flag Service               │
│  POST /evaluate                     │
└───────────┬─────────────────────────┘
            │
            ├─► Check Redis Cache
            │   Key: feature_flag:eval:{env}:{flag}:{user}:{hash}
            │   │
            │   ├─► Cache HIT → Return cached result (fast path)
            │   │
            │   └─► Cache MISS
            │       │
            │       ├─► OpenFeature SDK
            │       │   └─► Unleash Client API
            │       │       └─► Returns evaluation result
            │       │
            │       ├─► Cache result in Redis (TTL: 5 min)
            │       │
            │       └─► Publish to Kafka (optional)
            │
            └─► Return result to client
```

**Performance**: 
- Cache hit: ~1-2ms
- Cache miss: ~10-50ms (depending on Unleash response time)

### 2. Flag Listing Flow

```
Client Request
    │
    ▼
┌─────────────────────────────────────┐
│  Feature Flag Service               │
│  GET /feature-flags?environment=dev │
└───────────┬─────────────────────────┘
            │
            ├─► Check Redis Cache
            │   Key: feature_flags:list:{environment}
            │   │
            │   ├─► Cache HIT → Return cached list (fast path)
            │   │
            │   └─► Cache MISS
            │       │
            │       ├─► Unleash Admin API
            │       │   GET /api/admin/projects/default/features
            │       │   └─► Returns feature list (paginated)
            │       │
            │       ├─► Convert Unleash format → API format
            │       │   - Extract environment config
            │       │   - Determine enabled state
            │       │   - Extract metadata
            │       │
            │       ├─► Cache in Redis (TTL: 5 min)
            │       │
            │       └─► Apply pagination
            │
            └─► Return paginated results
```

**Performance**:
- Cache hit: ~1-2ms
- Cache miss: ~50-200ms (depending on number of flags)

### 3. Sync Flow

```
Client Request
    │
    ▼
┌─────────────────────────────────────┐
│  Feature Flag Service               │
│  POST /sync?environment=dev        │
└───────────┬─────────────────────────┘
            │
            ├─► Invalidate Redis Cache
            │   - Delete feature_flags:list:{env}
            │   - Delete all feature_flag:metadata:{env}:*
            │
            ├─► Fetch from Unleash Admin API
            │   GET /api/admin/projects/default/features
            │   └─► Paginate through all flags
            │
            ├─► Convert each feature
            │   - Match environment
            │   - Extract enabled state
            │   - Extract metadata
            │
            ├─► Cache in Redis
            │   - Store complete list
            │   - Store individual flag metadata
            │
            └─► Return sync count
```

## Redis Cache Structure

### Cache Keys

#### 1. Evaluation Results
```
Key Pattern: feature_flag:eval:{environment}:{flag_name}:{user_id}:{context_hash}

Example: feature_flag:eval:development:new-ui-enabled:user-123:a1b2c3d4e5f6

Value: {
  "flag_name": "new-ui-enabled",
  "value": true,
  "variant": null,
  "reason": "TARGETING_MATCH",
  "evaluated_at": "2024-01-15T10:30:00Z"
}

TTL: 300 seconds (5 minutes)
Purpose: Avoid re-evaluating same flag for same context
```

#### 2. Flag Metadata
```
Key Pattern: feature_flag:metadata:{environment}:{flag_name}

Example: feature_flag:metadata:development:new-ui-enabled

Value: {
  "id": 123456789,
  "name": "new-ui-enabled",
  "description": "Enable new UI",
  "is_enabled": true,
  "environment": "development",
  ...
}

TTL: 300 seconds (5 minutes)
Purpose: Fast lookup of individual flag details
```

#### 3. Flag List
```
Key Pattern: feature_flags:list:{environment}

Example: feature_flags:list:development

Value: {
  "flags": [
    {"id": 123456789, "name": "flag1", ...},
    {"id": 987654321, "name": "flag2", ...}
  ],
  "total": 2
}

TTL: 300 seconds (5 minutes)
Purpose: Fast listing without API calls
```

### Cache Invalidation

1. **On Sync**: All caches for an environment are invalidated
2. **Automatic**: Cache expires after TTL (5 minutes)
3. **Manual**: Call sync endpoint to force refresh

### Cache Benefits

- **Performance**: Reduces Unleash API calls by ~95%
- **Resilience**: Cached results available if Unleash is temporarily unavailable
- **Cost**: Reduces load on Unleash server
- **Speed**: Sub-millisecond response times for cached requests

## Redis Memory Usage

### Estimated Memory per Flag

- **Evaluation cache**: ~200 bytes per unique evaluation
- **Metadata cache**: ~500 bytes per flag
- **List cache**: ~1KB per flag in list

### Example Calculation

For 100 flags with 1000 unique evaluations:
- Evaluation cache: 1000 × 200 bytes = 200 KB
- Metadata cache: 100 × 500 bytes = 50 KB
- List cache: 100 × 1 KB = 100 KB
- **Total**: ~350 KB

With 5-minute TTL, memory usage is minimal and self-limiting.

## Unleash Integration

### API Endpoints Used

1. **Admin API** (for listing/syncing flags)
   - `GET /api/admin/projects/default/features`
   - Requires: Admin token
   - Returns: List of all features with environment configs

2. **Client API** (for evaluation)
   - Used by OpenFeature SDK internally
   - Requires: Client token (handled by SDK)
   - Returns: Evaluation results

### Token Types

- **Admin Token**: Required for Admin API operations
  - Format: `project:token` or `*:token`
  - Used for: Listing flags, syncing
  - Set in: `UNLEASH_API_TOKEN`

- **Client Token**: Used by SDK for evaluation
  - Format: `project:environment.token`
  - Used for: Flag evaluation
  - Handled by: OpenFeature SDK

## Performance Characteristics

### Evaluation Performance

| Scenario | Response Time | Cache Status |
|----------|--------------|--------------|
| Cache hit | 1-2ms | ✅ Cached |
| Cache miss (first time) | 10-50ms | ❌ Uncached |
| Cache miss (after TTL) | 10-50ms | ❌ Expired |

### Listing Performance

| Scenario | Response Time | Cache Status |
|----------|--------------|--------------|
| Cache hit | 1-2ms | ✅ Cached |
| Cache miss | 50-200ms | ❌ Uncached |
| Sync operation | 200-500ms | 🔄 Refreshing |

### Cache Hit Rates

Expected cache hit rates:
- **Evaluation**: 80-95% (depending on user diversity)
- **Listing**: 90-99% (flags don't change frequently)

## Monitoring

### Key Metrics to Monitor

1. **Cache Hit Rate**
   - High hit rate = Good performance
   - Low hit rate = Consider increasing TTL

2. **Redis Memory Usage**
   - Monitor memory consumption
   - Set alerts if approaching limits

3. **Unleash API Response Times**
   - Monitor Admin API latency
   - Alert if response times increase

4. **Sync Success Rate**
   - Monitor sync endpoint success
   - Alert on failures

### Logging

The service logs:
- Cache hits/misses
- API call details
- Sync operations
- Error conditions

Enable debug logging for detailed information:
```bash
LOG_LEVEL=DEBUG
```

## Troubleshooting

### Common Issues

1. **Flags not appearing**
   - Solution: Call sync endpoint
   - Check: Environment name matches

2. **Stale flag values**
   - Solution: Call sync endpoint
   - Check: Cache TTL settings

3. **403 Forbidden errors**
   - Solution: Use Admin token, not Client token
   - Check: Token permissions in Unleash UI

4. **Empty flag list**
   - Solution: Verify flags exist in Unleash UI
   - Check: Environment name matches

## Best Practices

1. **Cache Management**
   - Use appropriate TTL based on update frequency
   - Call sync after creating/updating flags
   - Monitor cache hit rates

2. **Token Management**
   - Use Admin tokens for Admin API
   - Rotate tokens regularly
   - Store tokens securely

3. **Performance**
   - Use bulk evaluation for multiple flags
   - Include user context for better targeting
   - Monitor Redis memory usage

4. **Reliability**
   - Handle cache misses gracefully
   - Implement retry logic for API calls
   - Monitor Unleash server health

