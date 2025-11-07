# Complete Vault Usage Guide for Config Service

## Table of Contents
1. [What is Vault and Why Use It?](#what-is-vault)
2. [How Vault Works in This System](#how-it-works)
3. [Initial Setup](#initial-setup)
4. [Configuration](#configuration)
5. [Using the Config Service with Vault](#using-config-service)
6. [Practical Examples](#practical-examples)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)
9. [Quick Reference](#quick-reference)

---

## What is Vault and Why Use It? {#what-is-vault}

**HashiCorp Vault** is a secrets management tool that securely stores and manages sensitive data like:
- API keys
- Database passwords
- Encryption keys
- Tokens and certificates

### Why Vault in This System?

1. **Single Source of Truth**: ALL configurations (encrypted and non-encrypted) are stored ONLY in Vault
2. **Security**: Encrypted values are never cached, always fetched fresh from Vault
3. **Versioning**: Vault KV v2 automatically tracks configuration history
4. **No Data Inconsistency**: Eliminates sync issues between databases
5. **Centralized Management**: One place to manage all service configurations

---

## How Vault Works in This System {#how-it-works}

### Architecture Overview

```
┌─────────────────┐
│  Config Service │
└────────┬────────┘
         │
         ├───► Vault (Single Source of Truth)
         │     └─── ALL configs stored here
         │
         ├───► Redis (Caching)
         │     └─── Only non-encrypted values cached
         │
         ├───► PostgreSQL
         │     └─── Feature flags & service registry (NOT configs)
         │
         └───► Kafka
               └─── Change notifications
```

### Storage Path Structure

All configurations are stored in Vault using this path pattern:
```
secret/data/{environment}/{service_name}/{key}
```

**Examples:**
- `secret/data/production/asr-service/api_key`
- `secret/data/development/llm-service/database_password`
- `secret/data/staging/auth-service/jwt_secret`

### Key Concepts

1. **ALL Configs in Vault**: Both encrypted and non-encrypted configs are stored in Vault
2. **No PostgreSQL Storage**: Configurations are NOT stored in PostgreSQL (only feature flags and registry)
3. **Smart Caching**: Non-encrypted values cached in Redis; encrypted values never cached
4. **Automatic Versioning**: Vault KV v2 tracks all changes automatically

---

## Initial Setup {#initial-setup}

### Step 1: Start Vault with Docker Compose

Vault is already configured in `docker-compose.yml`. To start it:

```bash
# Start all infrastructure services (including Vault)
./scripts/start-all.sh

# OR start just infrastructure
docker compose up -d vault

# OR use Makefile
make start
```

### Step 2: Verify Vault is Running

```bash
# Check Vault status
docker compose exec vault vault status

# Expected output:
# Key             Value
# ---             -----
# Seal Type       shamir
# Initialized     true
# Sealed          false
# ...

# Check health
./scripts/health-check-all.sh | grep vault
```

### Step 3: Verify KV v2 Secrets Engine

The initialization script should automatically enable KV v2. Verify:

```bash
# List secrets engines
docker compose exec vault vault secrets list

# Should show:
# Path          Type         Accessor              Description
# ----          ----         --------              -----------
# secret/       kv           kv_xxxxx              key-value secret storage
```

If `secret/` is not listed, enable it manually:

```bash
docker compose exec vault vault secrets enable -version=2 -path=secret kv
```

### Step 4: Get Vault Token

For development, the token is set in environment variables. Check your `.env` file:

```bash
# In docker-compose.yml, the token defaults to:
VAULT_ROOT_TOKEN=dev-root-token

# Or set it in your .env file:
echo "VAULT_ROOT_TOKEN=dev-root-token" >> .env
```

---

## Configuration {#configuration}

### Config Service Environment Variables

Edit `services/config-service/.env`:

```bash
# Vault Configuration
VAULT_ADDR=http://vault:8200          # Vault server address (Docker network)
VAULT_TOKEN=dev-root-token            # Your Vault token
VAULT_MOUNT_POINT=secret              # KV secrets engine mount point
VAULT_KV_VERSION=2                      # KV secrets engine version (must be 2)
```

**Important Notes:**
- `VAULT_ADDR` uses `vault:8200` (Docker service name) when running in containers
- For local development outside Docker, use `http://localhost:8200`
- `VAULT_TOKEN` must match the token from your Vault setup

### Verify Config Service Can Connect

```bash
# Check config service logs
docker compose logs config-service | grep -i vault

# Should see:
# Connected to Vault at http://vault:8200

# Or check health endpoint
curl http://localhost:8082/health
```

---

## Using the Config Service with Vault {#using-config-service}

### Creating Configurations

#### 1. Create a Non-Encrypted Configuration

```bash
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "model_path",
    "value": "/models/asr",
    "environment": "development",
    "service_name": "asr-service",
    "is_encrypted": false
  }'
```

**What happens:**
- Stored in Vault at `secret/data/development/asr-service/model_path`
- Cached in Redis for performance
- Can be retrieved quickly

#### 2. Create an Encrypted Configuration (Sensitive Data)

```bash
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "api_key",
    "value": "secret_api_key_12345",
    "environment": "production",
    "service_name": "asr-service",
    "is_encrypted": true
  }'
```

**What happens:**
- Stored in Vault at `secret/data/production/asr-service/api_key`
- **NOT cached** in Redis (security)
- Always fetched fresh from Vault on every request

### Retrieving Configurations

#### Get a Single Configuration

```bash
# Non-encrypted config
curl "http://localhost:8082/api/v1/config/model_path?environment=development&service_name=asr-service"

# Encrypted config
curl "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service"
```

**Response:**
```json
{
  "id": 0,
  "key": "api_key",
  "value": "secret_api_key_12345",
  "environment": "production",
  "service_name": "asr-service",
  "is_encrypted": true,
  "version": 1,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

**Note:** `id: 0` indicates the config is stored in Vault (not PostgreSQL).

#### List All Configurations

```bash
# List all configs for a service
curl "http://localhost:8082/api/v1/config?environment=production&service_name=asr-service"

# List configs for multiple services
curl "http://localhost:8082/api/v1/config?environment=production"

# Filter by specific keys
curl "http://localhost:8082/api/v1/config?environment=production&service_name=asr-service&keys[]=api_key&keys[]=model_path"
```

### Updating Configurations

```bash
curl -X PUT "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service" \
  -H 'Content-Type: application/json' \
  -d '{
    "value": "new_secret_api_key_67890",
    "is_encrypted": true
  }'
```

**What happens:**
- Old value is overwritten in Vault
- Vault KV v2 automatically creates a new version
- Cache is invalidated (if non-encrypted)
- Kafka event is published for notification

### Deleting Configurations

```bash
curl -X DELETE "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service"
```

**What happens:**
- Config is deleted from Vault
- Cache is invalidated
- Kafka event is published

### Viewing Configuration History

Vault KV v2 automatically tracks versions. To view history:

```bash
# Using Vault CLI directly
docker compose exec vault vault kv metadata get -versions secret/production/asr-service/api_key

# Or use config service endpoint (if implemented)
curl "http://localhost:8082/api/v1/config/api_key/history?environment=production&service_name=asr-service"
```

---

## Practical Examples {#practical-examples}

### Example 1: Setting Up Database Credentials

```bash
# Store database password (encrypted)
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "database_password",
    "value": "super_secret_db_password",
    "environment": "production",
    "service_name": "auth-service",
    "is_encrypted": true
  }'

# Store database host (non-encrypted, can be cached)
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "database_host",
    "value": "postgres:5432",
    "environment": "production",
    "service_name": "auth-service",
    "is_encrypted": false
  }'
```

### Example 2: Managing API Keys for Multiple Services

```bash
# ASR Service API Key
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "triton_api_key",
    "value": "asr_triton_key_123",
    "environment": "production",
    "service_name": "asr-service",
    "is_encrypted": true
  }'

# TTS Service API Key
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "triton_api_key",
    "value": "tts_triton_key_456",
    "environment": "production",
    "service_name": "tts-service",
    "is_encrypted": true
  }'

# LLM Service API Key
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "triton_api_key",
    "value": "llm_triton_key_789",
    "environment": "production",
    "service_name": "llm-service",
    "is_encrypted": true
  }'
```

### Example 3: Environment-Specific Configurations

```bash
# Development environment
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "log_level",
    "value": "DEBUG",
    "environment": "development",
    "service_name": "asr-service",
    "is_encrypted": false
  }'

# Production environment
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "log_level",
    "value": "INFO",
    "environment": "production",
    "service_name": "asr-service",
    "is_encrypted": false
  }'
```

### Example 4: Bulk Operations

```bash
# Get multiple configs at once
curl -X POST http://localhost:8082/api/v1/config/bulk \
  -H 'Content-Type: application/json' \
  -d '{
    "environment": "production",
    "service_name": "asr-service",
    "keys": ["api_key", "model_path", "database_host"]
  }'
```

### Example 5: Converting Between Encrypted and Non-Encrypted

```bash
# Convert encrypted to non-encrypted
curl -X PUT "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service" \
  -H 'Content-Type: application/json' \
  -d '{
    "value": "public_api_key_123",
    "is_encrypted": false
  }'

# Convert non-encrypted to encrypted
curl -X PUT "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service" \
  -H 'Content-Type: application/json' \
  -d '{
    "value": "secret_api_key_456",
    "is_encrypted": true
  }'
```

---

## Best Practices {#best-practices}

### 1. When to Use Encrypted vs Non-Encrypted

**Use `is_encrypted: true` for:**
- Passwords
- API keys
- Tokens
- Certificates
- Any sensitive data

**Use `is_encrypted: false` for:**
- Public configuration values
- File paths
- URLs
- Feature flags (use feature flags API instead)
- Non-sensitive settings

### 2. Environment Management

Always specify the environment:
- `development` - Local development
- `staging` - Pre-production testing
- `production` - Live environment

```bash
# Good: Always specify environment
curl -X POST ... -d '{"environment": "production", ...}'

# Bad: Missing environment
curl -X POST ... -d '{"key": "value", ...}'  # Will use default
```

### 3. Service Naming Convention

Use consistent service names:
- `asr-service`
- `tts-service`
- `llm-service`
- `auth-service`
- `config-service`
- etc.

### 4. Key Naming Convention

Use descriptive, consistent key names:
- `database_password` (not `db_pwd`)
- `api_key` (not `key`)
- `triton_endpoint` (not `endpoint`)

### 5. Token Management

**Development:**
- Use `dev-root-token` for local development
- Store in `.env` file (not committed to git)

**Production:**
- Use proper authentication (AppRole, Kubernetes auth)
- Rotate tokens regularly
- Never commit tokens to version control
- Use secret management systems

### 6. Monitoring

```bash
# Check Vault connection status
curl http://localhost:8082/health

# Monitor config service logs
docker compose logs -f config-service

# Check Vault logs
docker compose logs -f vault
```

### 7. Backup Strategy

```bash
# Backup Vault data (development)
docker compose exec vault vault kv list secret

# For production, use Vault's built-in backup features
# See: https://www.vaultproject.io/docs/commands/operator/raft
```

---

## Troubleshooting {#troubleshooting}

### Problem: Config Service Can't Connect to Vault

**Symptoms:**
- Logs show: "Vault not connected. Cannot write secret."
- API returns: "Cannot create configuration: Vault is not available"

**Solutions:**

1. **Check Vault is running:**
   ```bash
   docker compose ps vault
   # Should show: Up (healthy)
   ```

2. **Check Vault status:**
   ```bash
   docker compose exec vault vault status
   ```

3. **Verify environment variables:**
   ```bash
   docker compose exec config-service env | grep VAULT
   # Should show:
   # VAULT_ADDR=http://vault:8200
   # VAULT_TOKEN=dev-root-token
   ```

4. **Check network connectivity:**
   ```bash
   docker compose exec config-service ping -c 1 vault
   ```

5. **Verify token is correct:**
   ```bash
   # Test token manually
   docker compose exec vault vault token lookup
   ```

### Problem: KV v2 Secrets Engine Not Enabled

**Symptoms:**
- Error: "KV secrets engine not enabled at mount point"

**Solution:**
```bash
# Enable KV v2 manually
docker compose exec vault vault secrets enable -version=2 -path=secret kv

# Verify
docker compose exec vault vault secrets list
```

### Problem: Cannot Retrieve Config Values

**Symptoms:**
- API returns 404 for existing configs
- "Config not found" errors

**Solutions:**

1. **Verify config exists in Vault:**
   ```bash
   docker compose exec vault vault kv get secret/production/asr-service/api_key
   ```

2. **Check path format:**
   - Should be: `{environment}/{service_name}/{key}`
   - Example: `production/asr-service/api_key`

3. **Verify query parameters:**
   ```bash
   # Correct
   curl "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service"
   
   # Wrong (missing parameters)
   curl "http://localhost:8082/api/v1/config/api_key"
   ```

### Problem: Config Service Returns Wrong Values

**Symptoms:**
- Getting old values after update
- Cached values not refreshing

**Solutions:**

1. **For encrypted configs:** They're never cached, so this shouldn't happen
2. **For non-encrypted configs:** Clear Redis cache:
   ```bash
   docker compose exec redis redis-cli -a ${REDIS_PASSWORD} FLUSHDB
   ```

3. **Check Vault directly:**
   ```bash
   docker compose exec vault vault kv get secret/production/asr-service/api_key
   ```

### Problem: Vault Container Keeps Restarting

**Symptoms:**
- `docker compose ps` shows vault restarting
- Vault logs show errors

**Solutions:**

1. **Check logs:**
   ```bash
   docker compose logs vault
   ```

2. **Check disk space:**
   ```bash
   df -h
   ```

3. **Restart Vault:**
   ```bash
   docker compose restart vault
   ```

4. **Check health:**
   ```bash
   docker compose exec vault vault status
   ```

### Problem: Permission Denied Errors

**Symptoms:**
- "permission denied" when accessing Vault
- "unauthorized" errors

**Solutions:**

1. **Check token permissions:**
   ```bash
   docker compose exec vault vault token capabilities secret/data/production/asr-service/api_key
   ```

2. **Verify token is valid:**
   ```bash
   docker compose exec vault vault token lookup
   ```

3. **Use correct token:**
   - Check `VAULT_TOKEN` in config service `.env`
   - Must match `VAULT_ROOT_TOKEN` in main `.env`

---

## Quick Reference {#quick-reference}

### Essential Commands

```bash
# Start Vault
docker compose up -d vault

# Check Vault status
docker compose exec vault vault status

# List secrets engines
docker compose exec vault vault secrets list

# Get a secret directly from Vault
docker compose exec vault vault kv get secret/production/asr-service/api_key

# List all secrets for an environment
docker compose exec vault vault kv list secret/production

# Create config via API
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{"key":"key","value":"value","environment":"production","service_name":"service","is_encrypted":true}'

# Get config via API
curl "http://localhost:8082/api/v1/config/key?environment=production&service_name=service"

# Update config via API
curl -X PUT "http://localhost:8082/api/v1/config/key?environment=production&service_name=service" \
  -H 'Content-Type: application/json' \
  -d '{"value":"new_value","is_encrypted":true}'

# Delete config via API
curl -X DELETE "http://localhost:8082/api/v1/config/key?environment=production&service_name=service"
```

### Environment Variables Reference

```bash
# Config Service (.env)
VAULT_ADDR=http://vault:8200          # Vault server address
VAULT_TOKEN=dev-root-token            # Authentication token
VAULT_MOUNT_POINT=secret              # KV mount point
VAULT_KV_VERSION=2                     # KV version (must be 2)

# Docker Compose (.env)
VAULT_ROOT_TOKEN=dev-root-token       # Root token for dev mode
```

### API Endpoints Reference

```
POST   /api/v1/config                 # Create configuration
GET    /api/v1/config/{key}           # Get configuration
GET    /api/v1/config                 # List configurations
PUT    /api/v1/config/{key}           # Update configuration
DELETE /api/v1/config/{key}           # Delete configuration
GET    /api/v1/config/{key}/history   # Get configuration history
POST   /api/v1/config/bulk            # Bulk get configurations
GET    /health                        # Health check (includes Vault status)
```

### Path Structure Reference

```
Vault Path: secret/data/{environment}/{service_name}/{key}

Examples:
- secret/data/production/asr-service/api_key
- secret/data/development/llm-service/database_password
- secret/data/staging/auth-service/jwt_secret
```

---

## Summary

**Key Takeaways:**

1. ✅ **Vault is the single source of truth** for ALL configurations
2. ✅ **All configs** (encrypted and non-encrypted) are stored in Vault
3. ✅ **Encrypted configs** are never cached (always fresh from Vault)
4. ✅ **Non-encrypted configs** are cached in Redis for performance
5. ✅ **PostgreSQL** is NOT used for configurations (only feature flags & registry)
6. ✅ **Vault KV v2** provides automatic versioning
7. ✅ **Always specify** `environment` and `service_name` in API calls

**Next Steps:**

1. Start Vault: `docker compose up -d vault`
2. Configure config service: Set `VAULT_TOKEN` in `.env`
3. Create your first config: Use the API examples above
4. Monitor: Check logs and health endpoints regularly

For more details, see:
- [Vault Integration Guide](../services/config-service/docs/VAULT_INTEGRATION.md)
- [Config Service README](../services/config-service/README.md)

