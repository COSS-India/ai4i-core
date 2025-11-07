# NMT Service Configuration Management

## Overview

The NMT Service now uses **Config Service** for centralized configuration management. This eliminates confusion and data mismatches by having a single source of truth for configurations.

## Configuration Sources (Priority Order)

1. **Config Service** (Primary) - Centralized configuration management
2. **Environment Variables** (Fallback) - Used if Config Service is unavailable
3. **Hardcoded Defaults** (Last Resort) - Used if neither Config Service nor env vars are available

## Environment Variables (env.template)

Only essential variables remain in `env.template`:

### Required Variables

- `SERVICE_NAME` - Service name for registry (default: `nmt-service`)
- `SERVICE_PORT` - Service port (default: `8089`)
- `SERVICE_HOST` - Service hostname (default: `nmt-service`)
- `CONFIG_SERVICE_URL` - URL to Config Service (default: `http://config-service:8082`)
- `ENVIRONMENT` - Environment name: `development`, `staging`, or `production` (default: `development`)

### Optional Variables

- `SERVICE_PUBLIC_URL` - Public URL if different from Docker networking
- `SERVICE_INSTANCE_ID` - Custom instance identifier
- `LOG_LEVEL` - Logging level (default: `INFO`)

### Removed Variables (Now in Config Service)

The following variables have been **removed** from `env.template` and should be configured in Config Service:

- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `DATABASE_URL`
- `TRITON_ENDPOINT`, `TRITON_API_KEY`
- `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_HOUR`
- `MAX_BATCH_SIZE`, `MAX_TEXT_LENGTH`
- `DEFAULT_SOURCE_LANGUAGE`, `DEFAULT_TARGET_LANGUAGE`

## Setup Instructions

### 1. Create Configurations in Config Service

Use the provided script or curl commands:

```bash
# Using the unified management script
./manage-configs.sh setup development http://localhost:8082

# Or reset (clear then setup) for a clean setup
./manage-configs.sh reset development http://localhost:8082

# Or see CONFIG_SETUP.md for individual curl commands
```

### 2. Configure Environment Variables

Copy `env.template` to `.env` and update:

```bash
cp env.template .env
# Edit .env with your values
```

### 3. Start the Service

The service will:
1. Load configurations from Config Service
2. Fall back to environment variables if Config Service is unavailable
3. Use hardcoded defaults as last resort

## Configuration Loading Flow

```
Startup
  ↓
Load Configurations
  ↓
Try Config Service
  ├─ Success → Use Config Service values
  └─ Failure → Fall back to Environment Variables
      ├─ Found → Use Environment Variable
      └─ Not Found → Use Hardcoded Default
```

## Benefits

1. **Single Source of Truth** - All configurations in Config Service
2. **No Data Mismatches** - Eliminates confusion between env vars and config service
3. **Environment-Specific** - Different configs for dev/staging/production
4. **Secure** - Sensitive values (passwords, API keys) can be encrypted
5. **Centralized Management** - Update configs without redeploying services
6. **Fallback Support** - Service can still start if Config Service is temporarily unavailable

## Verifying Configurations

### List All Configurations

```bash
curl "http://config-service:8082/api/v1/config/?environment=development&service_name=nmt-service"
```

### Get Specific Configuration

```bash
curl "http://config-service:8082/api/v1/config/REDIS_HOST?environment=development&service_name=nmt-service"
```

### Update Configuration

```bash
curl -X PUT "http://config-service:8082/api/v1/config/REDIS_HOST?environment=development&service_name=nmt-service" \
  -H "Content-Type: application/json" \
  -d '{"value": "new-redis-host", "is_encrypted": false}'
```

## Troubleshooting

### Service Can't Connect to Config Service

- Check `CONFIG_SERVICE_URL` is correct
- Verify Config Service is running: `curl http://config-service:8082/health`
- Service will fall back to environment variables

### Configuration Not Found

- Verify configuration exists in Config Service
- Check `ENVIRONMENT` variable matches the environment where config was created
- Service will fall back to environment variables or defaults

### Configuration Mismatch

- Ensure configurations are created in Config Service
- Remove conflicting environment variables from `.env`
- Restart the service to reload configurations

## Migration Guide

If you're migrating from environment variables to Config Service:

1. **Export current env vars:**
   ```bash
   env | grep -E "REDIS_|DATABASE_|TRITON_|RATE_LIMIT_|MAX_" > current-configs.txt
   ```

2. **Create configurations in Config Service:**
   ```bash
   ./setup-configs.sh development http://config-service:8082
   ```

3. **Remove from .env:**
   - Remove all variables listed in "Removed Variables" section
   - Keep only essential variables (SERVICE_NAME, CONFIG_SERVICE_URL, etc.)

4. **Restart service:**
   ```bash
   docker compose restart nmt-service
   ```

5. **Verify:**
   - Check service logs for "Loaded X configurations from Config Service"
   - Verify service is working correctly

## Additional Resources

- `CONFIG_SETUP.md` - Detailed curl commands for creating configurations
- `setup-configs.sh` - Automated setup script
- Config Service Documentation - See `services/config-service/README.md`

