# Configuration Key Naming Convention

## Overview

All configuration keys in the Config Service **must be in UPPERCASE format** with underscores only. This convention is enforced at the API level to ensure consistency across all services.

## Rules

1. **All letters must be UPPERCASE**
2. **Only alphanumeric characters and underscores are allowed**
3. **Must contain at least one letter** (not just numbers)

## Valid Examples

✅ **Valid keys:**
- `REDIS_HOST`
- `DATABASE_URL`
- `TRITON_ENDPOINT`
- `TRITON_API_KEY`
- `RATE_LIMIT_PER_MINUTE`
- `MAX_BATCH_SIZE`
- `REDIS_123`
- `123_REDIS`

## Invalid Examples

❌ **Invalid keys:**
- `redis_host` - lowercase letters
- `RedisHost` - mixed case
- `REDIS-HOST` - hyphens not allowed
- `redis-host` - lowercase and hyphens
- `123_456` - no letters (only numbers)
- `REDIS.HOST` - dots not allowed
- `REDIS HOST` - spaces not allowed

## Validation

The Config Service automatically validates all configuration keys when creating or updating configurations. If a key doesn't follow the convention, the API will return a validation error:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "key"],
      "msg": "Configuration key 'redis_host' must be UPPERCASE. Example: 'REDIS_HOST', 'DATABASE_URL', 'TRITON_ENDPOINT'",
      "input": "redis_host"
    }
  ]
}
```

## Client-Side Normalization

The NMT Service's `ConfigurationClient` automatically normalizes keys to uppercase when fetching configurations. This means:

- If you request `redis_host`, it will be normalized to `REDIS_HOST`
- If you request `REDIS_HOST`, it will remain `REDIS_HOST`

However, **you should always use uppercase keys** when creating configurations to avoid confusion.

## Migration

If you have existing configurations with lowercase or mixed-case keys:

1. **Create new configurations with uppercase keys**
2. **Update your service code to use uppercase keys**
3. **Delete old lowercase/mixed-case configurations** (optional, to avoid confusion)

## Best Practices

1. **Always use UPPERCASE** when creating configurations
2. **Use descriptive names** with underscores: `REDIS_HOST` not `RH`
3. **Be consistent** across all services
4. **Document your keys** in service documentation

## Examples

### Creating a Configuration

```bash
# ✅ Correct
curl -X POST http://localhost:8082/api/v1/config/ \
  -H "Content-Type: application/json" \
  -d '{
    "key": "REDIS_HOST",
    "value": "redis",
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# ❌ Incorrect - will be rejected
curl -X POST http://localhost:8082/api/v1/config/ \
  -H "Content-Type: application/json" \
  -d '{
    "key": "redis_host",
    "value": "redis",
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'
```

### Fetching a Configuration

```python
# Both work (client normalizes to uppercase)
config_client = ConfigurationClient()
value1 = await config_client.get_config("REDIS_HOST")  # ✅
value2 = await config_client.get_config("redis_host")  # ✅ (normalized to REDIS_HOST)
```

## See Also

- [Config Service README](../README.md) - Main documentation
- [NMT Service Config Setup](../../nmt-service/CONFIG_SETUP.md) - Example configuration setup

