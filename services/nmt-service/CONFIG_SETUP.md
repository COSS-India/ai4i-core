# NMT Service Configuration Setup Guide

This guide shows how to create configurations for the NMT Service in the Config Service.

## Overview

The NMT Service now uses the Config Service for centralized configuration management. Most environment variables have been moved to the Config Service to avoid confusion and data mismatches.

## Environment Variables (env.template)

Only essential variables remain in `env.template`:
- `SERVICE_NAME` - Service name for registry
- `SERVICE_PORT` - Service port
- `SERVICE_HOST` - Service hostname
- `CONFIG_SERVICE_URL` - URL to Config Service
- `ENVIRONMENT` - Environment name (development/staging/production)
- `LOG_LEVEL` - Logging level (optional)

## Configuration Setup

### Option 1: Using the Unified Management Script

```bash
# Setup configurations (creates all configs)
./manage-configs.sh setup development http://localhost:8082

# Clear all configurations
./manage-configs.sh clear development http://localhost:8082

# Reset (clear then setup) - useful for clean setup
./manage-configs.sh reset development http://localhost:8082

# For production environment
./manage-configs.sh setup production http://config-service:8082
```

### Option 2: Using cURL Commands

Replace the following placeholders:
- `{ENVIRONMENT}` - development, staging, or production
- `{CONFIG_SERVICE_URL}` - http://config-service:8082 or http://localhost:8082

#### Redis Configuration

```bash
# REDIS_HOST
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "REDIS_HOST",
    "value": "redis",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# REDIS_PORT
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "REDIS_PORT",
    "value": "6379",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# REDIS_PASSWORD (encrypted)
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "REDIS_PASSWORD",
    "value": "redis_secure_password_2024",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": true
  }'
```

#### PostgreSQL Configuration

```bash
# DATABASE_URL (encrypted)
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "DATABASE_URL",
    "value": "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": true
  }'
```

#### Triton Inference Server Configuration

```bash
# TRITON_ENDPOINT
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "TRITON_ENDPOINT",
    "value": "13.200.133.97:8000",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# TRITON_API_KEY (encrypted)
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "TRITON_API_KEY",
    "value": "1b69e9a1a24466c85e4bbca3c5295f50",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": true
  }'
```

#### Rate Limiting Configuration

```bash
# RATE_LIMIT_PER_MINUTE
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "RATE_LIMIT_PER_MINUTE",
    "value": "60",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# RATE_LIMIT_PER_HOUR
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "RATE_LIMIT_PER_HOUR",
    "value": "1000",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'
```

#### NMT Service Configuration

```bash
# MAX_BATCH_SIZE
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "MAX_BATCH_SIZE",
    "value": "90",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# MAX_TEXT_LENGTH
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "MAX_TEXT_LENGTH",
    "value": "10000",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# DEFAULT_SOURCE_LANGUAGE
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "DEFAULT_SOURCE_LANGUAGE",
    "value": "en",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# DEFAULT_TARGET_LANGUAGE
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "DEFAULT_TARGET_LANGUAGE",
    "value": "hi",
    "environment": "{ENVIRONMENT}",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'
```

## Verify Configurations

To list all configurations for the NMT service:

```bash
curl "{CONFIG_SERVICE_URL}/api/v1/config/?environment={ENVIRONMENT}&service_name=nmt-service"
```

To get a specific configuration:

```bash
curl "{CONFIG_SERVICE_URL}/api/v1/config/{KEY}?environment={ENVIRONMENT}&service_name=nmt-service"
```

## Update Configuration

To update an existing configuration:

```bash
curl -X PUT "{CONFIG_SERVICE_URL}/api/v1/config/{KEY}?environment={ENVIRONMENT}&service_name=nmt-service" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "new_value",
    "is_encrypted": false
  }'
```

## Fallback Behavior

The NMT Service will:
1. First try to load configurations from Config Service
2. Fall back to environment variables if Config Service is unavailable
3. Use hardcoded defaults as a last resort

This ensures the service can start even if Config Service is temporarily unavailable, but configurations should be managed through Config Service to avoid data mismatches.

## Environment-Specific Configurations

Create separate configurations for each environment:
- `development` - For local development
- `staging` - For staging/testing
- `production` - For production

Use the same curl commands but change the `environment` parameter.

