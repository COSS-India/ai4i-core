# Feature Flags Implementation Guide

## Overview

The Feature Flags system provides a centralized, environment-aware mechanism for controlling feature rollouts across microservices. It supports progressive rollouts, user targeting, and comprehensive audit trails.

## Table of Contents

1. [Architecture](#architecture)
2. [Core Concepts](#core-concepts)
3. [Database Schema](#database-schema)
4. [API Reference](#api-reference)
5. [Evaluation Logic](#evaluation-logic)
6. [Caching Strategy](#caching-strategy)
7. [Event Publishing](#event-publishing)
8. [Audit Trail](#audit-trail)
9. [Configuration](#configuration)
10. [Best Practices](#best-practices)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Config Service                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Router     │  │   Service    │  │  Repository  │    │
│  │  (FastAPI)   │→ │   (Business) │→ │  (Database)  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│         │                  │                  │            │
│         └──────────────────┼──────────────────┘            │
│                            │                               │
│         ┌──────────────────┼──────────────────┐           │
│         │                  │                  │           │
│  ┌──────▼──────┐  ┌────────▼──────┐  ┌───────▼──────┐   │
│  │    Redis    │  │  PostgreSQL   │  │    Kafka     │   │
│  │  (Caching)  │  │  (Persistence)│  │  (Events)    │   │
│  └─────────────┘  └───────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Create/Update Flag**: API Request → Service → Repository → Database → Cache Invalidation → Kafka Event
2. **Evaluate Flag**: API Request → Service → Cache Check → Repository (if miss) → Cache Store → Response
3. **History Tracking**: Update Operation → Repository → History Table → Audit Trail

## Core Concepts

### 1. Feature Flag

A feature flag is a named configuration that controls whether a feature is enabled for specific users or environments.

**Properties:**
- `name`: Unique identifier (unique per environment)
- `environment`: One of `development`, `staging`, `production`
- `is_enabled`: Master switch for the flag
- `rollout_percentage`: Percentage of users who should see the feature (0-100)
- `target_users`: Specific user IDs that always have access
- `description`: Human-readable description

### 2. Environment Isolation

Each environment (development, staging, production) maintains its own set of feature flags. The same flag name can exist in multiple environments with different configurations.

**Example:**
```json
{
  "name": "new_checkout_flow",
  "environment": "development",
  "is_enabled": true,
  "rollout_percentage": 100.0
}
```

```json
{
  "name": "new_checkout_flow",
  "environment": "production",
  "is_enabled": true,
  "rollout_percentage": 10.0
}
```

### 3. Evaluation Strategy

Flags are evaluated in this order:
1. **Flag Not Found** → `false`
2. **Flag Disabled** → `false`
3. **User in Target List** → `true` (highest priority)
4. **Rollout Percentage** → Deterministic hash-based evaluation

## Database Schema

### Feature Flags Table

```sql
CREATE TABLE feature_flags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_enabled BOOLEAN DEFAULT false,
    rollout_percentage VARCHAR(255),
    target_users JSONB,
    environment VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, environment)
);
```

**Key Constraints:**
- `UNIQUE(name, environment)`: Allows same name in different environments
- `rollout_percentage`: Stored as VARCHAR for DECIMAL compatibility
- `target_users`: JSONB array of user IDs

### Feature Flag History Table

```sql
CREATE TABLE feature_flag_history (
    id SERIAL PRIMARY KEY,
    feature_flag_id INTEGER REFERENCES feature_flags(id) ON DELETE CASCADE,
    old_is_enabled BOOLEAN,
    new_is_enabled BOOLEAN,
    old_rollout_percentage VARCHAR(255),
    new_rollout_percentage VARCHAR(255),
    old_target_users JSONB,
    new_target_users JSONB,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
- `idx_feature_flag_history_flag_id`: Fast history lookups
- `idx_feature_flag_history_changed_at`: Time-based queries
- `idx_feature_flags_name_env`: Fast flag lookups

## API Reference

### Base URL
```
http://config-service:8082/api/v1/feature-flags
```

### Endpoints

#### 1. Create Feature Flag

**POST** `/api/v1/feature-flags/`

**Request Body:**
```json
{
  "name": "new_ui",
  "description": "New user interface",
  "is_enabled": true,
  "rollout_percentage": 50.0,
  "target_users": ["user123", "user456"],
  "environment": "development"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "name": "new_ui",
  "description": "New user interface",
  "is_enabled": true,
  "rollout_percentage": 50.0,
  "target_users": ["user123", "user456"],
  "environment": "development",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

#### 2. Get Feature Flag

**GET** `/api/v1/feature-flags/{name}?environment={env}`

**Response:** `200 OK`
```json
{
  "id": 1,
  "name": "new_ui",
  "description": "New user interface",
  "is_enabled": true,
  "rollout_percentage": 50.0,
  "target_users": ["user123"],
  "environment": "development",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

#### 3. List Feature Flags

**GET** `/api/v1/feature-flags/?environment={env}&enabled={bool}&limit=50&offset=0`

**Query Parameters:**
- `environment` (optional): Filter by environment
- `enabled` (optional): Filter by enabled status (`true`/`false`)
- `limit` (default: 50): Maximum results
- `offset` (default: 0): Pagination offset

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "name": "new_ui",
    "is_enabled": true,
    "rollout_percentage": 50.0,
    "environment": "development",
    ...
  }
]
```

#### 4. Update Feature Flag

**PUT** `/api/v1/feature-flags/{name}?environment={env}`

**Request Body:**
```json
{
  "is_enabled": true,
  "rollout_percentage": 75.0,
  "target_users": ["user123", "user456", "user789"]
}
```

**Response:** `200 OK` (same as Get Feature Flag)

#### 5. Delete Feature Flag

**DELETE** `/api/v1/feature-flags/{name}?environment={env}`

**Response:** `204 No Content`

#### 6. Evaluate Feature Flag

**POST** `/api/v1/feature-flags/evaluate`

**Request Body:**
```json
{
  "flag_name": "new_ui",
  "user_id": "user123",
  "environment": "development"
}
```

**Response:** `200 OK`
```json
{
  "enabled": true,
  "reason": "user_targeted"
}
```

**Possible Reasons:**
- `flag_not_found`: Flag doesn't exist
- `flag_disabled`: Flag is disabled
- `user_targeted`: User is in target_users list
- `full_rollout`: Rollout percentage is 100%
- `zero_rollout`: Rollout percentage is 0%
- `percentage_rollout`: User included via percentage
- `percentage_excluded`: User excluded via percentage

#### 7. Batch Evaluate

**POST** `/api/v1/feature-flags/evaluate/batch?user_id={uid}&environment={env}`

**Request Body:**
```json
["new_ui", "dark_mode", "beta_features"]
```

**Response:** `200 OK`
```json
{
  "new_ui": {
    "enabled": true,
    "reason": "percentage_rollout"
  },
  "dark_mode": {
    "enabled": false,
    "reason": "flag_disabled"
  },
  "beta_features": {
    "enabled": true,
    "reason": "user_targeted"
  }
}
```

#### 8. Get Flag History

**GET** `/api/v1/feature-flags/{name}/history?environment={env}&limit=50`

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "old_is_enabled": false,
    "new_is_enabled": true,
    "old_rollout_percentage": "0.0",
    "new_rollout_percentage": "50.0",
    "old_target_users": null,
    "new_target_users": ["user123"],
    "changed_by": "admin@example.com",
    "changed_at": "2024-01-15T11:00:00Z"
  }
]
```

## Evaluation Logic

### Deterministic Rollout

The system uses consistent hashing to ensure the same user always gets the same result for a given flag.

**Algorithm:**
```python
hash = SHA256(f"{flag_name}:{user_id}")
bucket = int(hash[:8], 16) % 100
enabled = bucket < rollout_percentage
```

**Properties:**
- **Deterministic**: Same user + same flag = same result
- **Consistent**: User won't flip between enabled/disabled
- **Distributed**: Even distribution across 0-100 buckets

### Evaluation Flow

```
┌─────────────────┐
│  Evaluate Flag  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Flag Exists?    │──No──→ Return: false, "flag_not_found"
└────────┬────────┘
         │Yes
         ▼
┌─────────────────┐
│ Flag Enabled?   │──No──→ Return: false, "flag_disabled"
└────────┬────────┘
         │Yes
         ▼
┌─────────────────┐
│ User Targeted?  │──Yes─→ Return: true, "user_targeted"
└────────┬────────┘
         │No
         ▼
┌─────────────────┐
│ Rollout = 100%? │──Yes─→ Return: true, "full_rollout"
└────────┬────────┘
         │No
         ▼
┌─────────────────┐
│ Rollout = 0%?    │──Yes─→ Return: false, "zero_rollout"
└────────┬────────┘
         │No
         ▼
┌─────────────────┐
│ Hash Evaluation │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Bucket │
    │ < %?   │
    └────┬────┘
    ┌────┴────┐
    │  Yes   │──→ Return: true, "percentage_rollout"
    │  No    │──→ Return: false, "percentage_excluded"
    └────────┘
```

## Caching Strategy

### Cache Keys

- **Flag Data**: `feature_flag:{environment}:{name}`
- **Evaluation Result**: `flag_eval:{environment}:{name}:{user_id}`

### Cache TTL

- Default: 300 seconds (5 minutes)
- Configurable via `FEATURE_FLAG_CACHE_TTL` environment variable

### Cache Invalidation

Cache is invalidated on:
- Flag creation
- Flag update
- Flag deletion

### Cache Benefits

- **Performance**: Reduces database queries by ~90%
- **Consistency**: Evaluation results cached per user
- **Scalability**: Handles high request volumes

## Event Publishing

### Kafka Events

All flag changes are published to Kafka topic: `feature-flag-updates`

**Event Types:**

1. **feature_flag_created**
```json
{
  "event_type": "feature_flag_created",
  "flag_name": "new_ui",
  "environment": "development",
  "is_enabled": true,
  "rollout_percentage": 50.0,
  "target_users": ["user123"]
}
```

2. **feature_flag_updated**
```json
{
  "event_type": "feature_flag_updated",
  "flag_name": "new_ui",
  "environment": "development",
  "is_enabled": true,
  "rollout_percentage": 75.0,
  "target_users": ["user123", "user456"]
}
```

3. **feature_flag_deleted**
```json
{
  "event_type": "feature_flag_deleted",
  "flag_name": "new_ui",
  "environment": "development"
}
```

### Event Consumers

Microservices can subscribe to these events to:
- Update local caches
- Trigger feature-specific logic
- Update analytics/metrics
- Send notifications

## Audit Trail

### History Tracking

Every flag update creates a history entry tracking:
- `is_enabled` changes
- `rollout_percentage` changes
- `target_users` changes
- Timestamp and optional `changed_by` field

### Use Cases

- **Compliance**: Track all feature changes
- **Debugging**: Understand why a feature behaved differently
- **Rollback**: Identify previous configurations
- **Analytics**: Analyze feature adoption patterns

## Configuration

### Environment Variables

```bash
# Feature Flag Configuration
FEATURE_FLAG_CACHE_TTL=300  # Cache TTL in seconds

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_TOPIC_FEATURE_FLAG_UPDATES=feature-flag-updates

# Database Configuration
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/config_db

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=redis_secure_password_2024
```

## Best Practices

### 1. Naming Conventions

- Use descriptive, lowercase names with underscores
- Examples: `new_checkout_flow`, `dark_mode`, `beta_features`
- Avoid: `flag1`, `test`, `temp`

### 2. Rollout Strategy

**Recommended Rollout:**
1. Start with 0% (disabled)
2. Enable for target users (internal testing)
3. Gradual rollout: 1% → 5% → 25% → 50% → 100%
4. Monitor metrics at each stage
5. Rollback if issues detected

### 3. Environment Management

- **Development**: Test flags freely
- **Staging**: Mirror production flags for testing
- **Production**: Use conservative rollouts

### 4. User Targeting

- Use for beta testers, VIP users, or internal team
- Keep target lists small (< 100 users)
- For larger groups, use percentage rollout

### 5. Monitoring

- Track evaluation metrics
- Monitor error rates
- Set up alerts for flag changes
- Review history regularly

### 6. Cleanup

- Remove unused flags
- Archive old flags
- Document flag purposes
- Regular audits

### 7. Security

- Validate user IDs
- Rate limit evaluation endpoints
- Audit all flag changes
- Use environment-specific access controls

## Error Handling

### Common Errors

**404 Not Found**
```json
{
  "detail": "Feature flag not found"
}
```

**400 Bad Request**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "rollout_percentage"],
      "msg": "rollout_percentage must be between 0 and 100"
    }
  ]
}
```

**409 Conflict**
```json
{
  "detail": "Feature flag already exists"
}
```

**500 Internal Server Error**
- Check database connectivity
- Verify Redis is available
- Review service logs

## Performance Considerations

### Optimization Tips

1. **Use Batch Evaluation**: Evaluate multiple flags in one request
2. **Cache Aggressively**: Leverage Redis caching
3. **Index Properly**: Database indexes on (name, environment)
4. **Connection Pooling**: Reuse database connections
5. **Async Operations**: Non-blocking I/O for better throughput

### Expected Performance

- **Single Evaluation**: < 10ms (with cache), < 50ms (without cache)
- **Batch Evaluation**: < 50ms for 10 flags
- **Flag Creation**: < 100ms
- **Flag Update**: < 100ms

## Troubleshooting

### Flag Not Working

1. Check flag exists: `GET /api/v1/feature-flags/{name}?environment={env}`
2. Verify flag is enabled: `is_enabled: true`
3. Check rollout percentage
4. Verify user ID format
5. Check cache: Clear Redis cache if needed

### Evaluation Inconsistencies

1. Verify deterministic hashing (same user = same result)
2. Check for multiple environments
3. Review target_users list
4. Check cache TTL settings

### Database Issues

1. Verify connection string
2. Check table exists: `\d feature_flags`
3. Verify constraints: `SELECT * FROM pg_constraint WHERE conrelid = 'feature_flags'::regclass;`
4. Check indexes: `\d+ feature_flags`

## Migration Guide

If upgrading from an older version, see:
- `infrastructure/postgres/migrate-feature-flags-constraint.sql`
- `services/config-service/TEST_FIXES.md`

## Related Documentation

- [Feature Flags Integration Guide](./FEATURE_FLAGS_INTEGRATION.md) - How to integrate in microservices
- [Config Service README](../README.md) - Service overview
- [Feature Flags Implementation](../FEATURE_FLAGS_IMPLEMENTATION.md) - Implementation details

