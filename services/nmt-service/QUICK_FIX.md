# Quick Fix: Missing Configurations

## Issue

You're missing Redis and PostgreSQL configurations, and the Triton configs have the wrong case.

## Problem

1. **Missing Configs:**
   - `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
   - `DATABASE_URL`
   - `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_HOUR`
   - `MAX_BATCH_SIZE`, `MAX_TEXT_LENGTH`
   - `DEFAULT_SOURCE_LANGUAGE`, `DEFAULT_TARGET_LANGUAGE`

2. **Case Mismatch:**
   - You have: `triton_endpoint` and `triton_api_key` (lowercase)
   - Code expects: `TRITON_ENDPOINT` and `TRITON_API_KEY` (uppercase)

## Quick Fix

### Option 1: Use the Fix Script

```bash
cd services/nmt-service
./fix-missing-configs.sh development http://config-service:8082
```

### Option 2: Manual cURL Commands

Replace `{CONFIG_SERVICE_URL}` with your config service URL (e.g., `http://config-service:8082` or `http://localhost:8082`)

#### Redis Configuration

```bash
# REDIS_HOST
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "REDIS_HOST",
    "value": "redis",
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# REDIS_PORT
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "REDIS_PORT",
    "value": "6379",
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# REDIS_PASSWORD (encrypted)
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "REDIS_PASSWORD",
    "value": "redis_secure_password_2024",
    "environment": "development",
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
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": true
  }'
```

#### Fix Triton Configuration (Uppercase)

```bash
# TRITON_ENDPOINT (uppercase - you have lowercase version)
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "TRITON_ENDPOINT",
    "value": "13.200.133.97:8000",
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# TRITON_API_KEY (uppercase - you have lowercase version)
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "TRITON_API_KEY",
    "value": "1b69e9a1a24466c85e4bbca3c5295f50",
    "environment": "development",
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
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# RATE_LIMIT_PER_HOUR
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "RATE_LIMIT_PER_HOUR",
    "value": "1000",
    "environment": "development",
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
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# MAX_TEXT_LENGTH
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "MAX_TEXT_LENGTH",
    "value": "10000",
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# DEFAULT_SOURCE_LANGUAGE
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "DEFAULT_SOURCE_LANGUAGE",
    "value": "en",
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'

# DEFAULT_TARGET_LANGUAGE
curl -X POST "{CONFIG_SERVICE_URL}/api/v1/config/" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "DEFAULT_TARGET_LANGUAGE",
    "value": "hi",
    "environment": "development",
    "service_name": "nmt-service",
    "is_encrypted": false
  }'
```

## Verify

After creating all configs, verify they exist:

```bash
curl "{CONFIG_SERVICE_URL}/api/v1/config/?environment=development&service_name=nmt-service"
```

You should now see all the required configurations:
- ✅ REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
- ✅ DATABASE_URL
- ✅ TRITON_ENDPOINT, TRITON_API_KEY (uppercase)
- ✅ RATE_LIMIT_PER_MINUTE, RATE_LIMIT_PER_HOUR
- ✅ MAX_BATCH_SIZE, MAX_TEXT_LENGTH
- ✅ DEFAULT_SOURCE_LANGUAGE, DEFAULT_TARGET_LANGUAGE

## Optional: Clean Up

You can delete the lowercase versions if you want:

```bash
# Delete lowercase triton_endpoint
curl -X DELETE "{CONFIG_SERVICE_URL}/api/v1/config/triton_endpoint?environment=development&service_name=nmt-service"

# Delete lowercase triton_api_key
curl -X DELETE "{CONFIG_SERVICE_URL}/api/v1/config/triton_api_key?environment=development&service_name=nmt-service"
```

