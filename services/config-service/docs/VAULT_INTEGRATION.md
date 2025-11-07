# Vault Integration Guide

## Overview

The Configuration Management Service uses HashiCorp Vault as the **single source of truth** for **ALL configurations** (both encrypted and non-encrypted). This eliminates data inconsistency and simplifies the architecture. PostgreSQL is still used for feature flags and service registry, but not for configurations.

## Architecture

### Storage Strategy

- **ALL Configurations** (both encrypted and non-encrypted):
  - **Single Source of Truth**: Stored **ONLY** in HashiCorp Vault
  - **No PostgreSQL Entry**: Configurations are not stored in PostgreSQL
  - **Vault KV v2**: Uses Vault's built-in versioning for history tracking
  - **Caching**: Non-encrypted values are cached in Redis for performance
  - **Security**: Encrypted values are never cached in Redis

**Note:** PostgreSQL is still used for:
- Feature flags (different data model with rollout percentages, target users)
- Service registry (different data model with health checks, metadata)

### Vault Secret Path Structure

Secrets are stored in Vault using the following path structure:
```
secret/data/{environment}/{service_name}/{key}
```

For example:
- `secret/data/production/asr-service/api_key`
- `secret/data/development/llm-service/database_password`

## Configuration

### Environment Variables

Add the following environment variables to enable Vault integration:

```bash
# Vault Configuration
VAULT_ADDR=http://vault:8200          # Vault server address
VAULT_TOKEN=your_vault_token_here      # Vault authentication token
VAULT_MOUNT_POINT=secret              # KV secrets engine mount point (default: secret)
VAULT_KV_VERSION=2                     # KV secrets engine version (default: 2)
```

### Vault Setup

1. **Start Vault Server**:
   ```bash
   vault server -dev
   ```

2. **Enable KV Secrets Engine** (if not already enabled):
   ```bash
   vault secrets enable -version=2 -path=secret kv
   ```

3. **Create a Token** (for production, use proper authentication):
   ```bash
   vault token create -policy=default
   ```

4. **Set Environment Variables**:
   ```bash
   export VAULT_ADDR=http://localhost:8200
   export VAULT_TOKEN=<your-token>
   ```

## Features

### Automatic Vault Integration

- **Single Source of Truth**: **ALL configs** (encrypted and non-encrypted) are stored **ONLY** in Vault
- **Transparent Storage**: All configurations are automatically stored in Vault
- **Automatic Retrieval**: All configurations are retrieved from Vault
- **No Fallback**: If Vault is unavailable, config operations will fail (prevents inconsistency)
- **Smart Caching**: Non-encrypted values are cached in Redis; encrypted values are never cached
- **Versioning**: Vault KV v2 provides built-in versioning for all configs
- **Automatic Cleanup**: When deleting configs, they are removed from Vault

### Security Features

- **No Value Caching**: Encrypted configuration values are never cached in Redis
- **Fresh Retrieval**: Every request for an encrypted config fetches the latest value from Vault
- **Audit Trail**: All configuration changes are logged in PostgreSQL history, even for Vault-stored values
- **Metadata Separation**: Sensitive values in Vault, metadata in PostgreSQL

## Usage Examples

### Creating an Encrypted Configuration

```bash
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "database_password",
    "value": "super_secret_password_123",
    "environment": "production",
    "service_name": "auth-service",
    "is_encrypted": true
  }'
```

**What happens:**
1. Value `super_secret_password_123` is stored in Vault at `secret/data/production/auth-service/database_password`
2. **No PostgreSQL entry** - all configs are stored ONLY in Vault
3. Response returns the actual value from Vault

### Retrieving an Encrypted Configuration

```bash
curl "http://localhost:8082/api/v1/config/database_password?environment=production&service_name=auth-service"
```

**What happens:**
1. Retrieves config from Vault (single source of truth)
2. Response includes the actual value from Vault
3. Non-encrypted values may be cached in Redis for performance

### Updating an Encrypted Configuration

```bash
curl -X PUT "http://localhost:8082/api/v1/config/database_password?environment=production&service_name=auth-service" \
  -H 'Content-Type: application/json' \
  -d '{
    "value": "new_secret_password_456",
    "is_encrypted": true
  }'
```

**What happens:**
1. New value is written to Vault (overwrites existing)
2. **No PostgreSQL update** - all configs exist only in Vault
3. Vault KV v2 handles versioning internally

### Converting Between Encrypted and Non-Encrypted

**Encrypted → Non-Encrypted:**
```bash
curl -X PUT "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service" \
  -H 'Content-Type: application/json' \
  -d '{
    "value": "public_api_key_123",
    "is_encrypted": false
  }'
```

**What happens:**
1. Config is updated in Vault with `is_encrypted=false`
2. Config remains in Vault (single source of truth)
3. Non-encrypted value can now be cached in Redis

**Non-Encrypted → Encrypted:**
```bash
curl -X PUT "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service" \
  -H 'Content-Type: application/json' \
  -d '{
    "value": "secret_api_key_456",
    "is_encrypted": true
  }'
```

**What happens:**
1. Config is updated in Vault with `is_encrypted=true`
2. Config remains in Vault (single source of truth)
3. Encrypted value is no longer cached in Redis

### Deleting an Encrypted Configuration

```bash
curl -X DELETE "http://localhost:8082/api/v1/config/database_password?environment=production&service_name=auth-service"
```

**What happens:**
1. Config is deleted from Vault (single source of truth)
2. Cache is invalidated in Redis
3. Kafka event is published for notification

## API Behavior

### Create Configuration

**Request:**
```json
{
  "key": "secret_key",
  "value": "my_secret_value",
  "environment": "production",
  "service_name": "my-service",
  "is_encrypted": true
}
```

**Response:**
```json
{
  "id": 1,
  "key": "secret_key",
  "value": "my_secret_value",
  "environment": "production",
  "service_name": "my-service",
  "is_encrypted": true,
  "version": 1,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

**Note:** 
- All configs are stored ONLY in Vault (single source of truth)
- No PostgreSQL entries for configurations
- The response always returns the actual value from Vault

### Get Configuration

**Request:**
```
GET /api/v1/config/secret_key?environment=production&service_name=my-service
```

**Response:**
```json
{
  "id": 0,
  "key": "secret_key",
  "value": "my_secret_value",
  "environment": "production",
  "service_name": "my-service",
  "is_encrypted": true,
  "version": 1,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

**Note:** 
- All configs: `id=0` (no database ID since stored only in Vault)
- Encrypted values are fetched from Vault on every request (not cached)
- Non-encrypted values may be cached in Redis for performance

### List Configurations

**Request:**
```
GET /api/v1/config?environment=production&service_name=my-service
```

**Response:**
```json
{
  "items": [
    {
      "id": 1,
      "key": "secret_key",
      "value": "my_secret_value",
      "environment": "production",
      "service_name": "my-service",
      "is_encrypted": true,
      "version": 1,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

**Note:** 
- All configs are fetched from Vault (single source of truth)
- All configs have `id=0` (no database ID)
- Pagination is applied to the Vault results

## Error Handling

### Vault Connection Failures

If Vault is unavailable or authentication fails:

1. **During Creation/Update:**
   - **Operation fails** with an error (prevents inconsistency)
   - Error message: "Cannot create/update configuration: Vault is not available"
   - Service requires Vault to be available for all config operations

2. **During Retrieval:**
   - If config exists in Vault but Vault is unavailable:
     - Config is not found (returns 404)
     - No fallback (ensures single source of truth)

3. **Service Status:**
   - Check `/api/v1/config/status` endpoint
   - `vault_enabled` field indicates Vault connection status
   - All config operations require Vault to be available

### Best Practices

1. **Always use Vault for sensitive data:**
   - API keys, passwords, tokens
   - Database credentials
   - Third-party service secrets

2. **Monitor Vault connectivity:**
   - Check service logs for Vault connection warnings
   - Monitor `/api/v1/config/status` endpoint
   - Set up alerts for Vault connection failures

3. **Use proper Vault authentication:**
   - In production, use AppRole, Kubernetes auth, or other secure methods
   - Avoid long-lived tokens
   - Rotate tokens regularly

4. **Backup Vault data:**
   - Ensure Vault data is backed up
   - Consider Vault replication for high availability

## Troubleshooting

### Issue: Cannot create configs

**Symptoms:**
- Error: "Cannot create configuration: Vault is not available"
- Config creation fails for all configs

**Solutions:**
1. Check `VAULT_ADDR` is correct
2. Verify `VAULT_TOKEN` is valid and has proper permissions
3. Ensure KV secrets engine is enabled at the mount point
4. Check Vault server is running and accessible
5. Verify Vault connection in service logs

### Issue: Cannot retrieve config values

**Symptoms:**
- API returns 404 for configs
- Config not found even though it should exist

**Solutions:**
1. Verify secret exists in Vault:
   ```bash
   vault kv get secret/production/my-service/my_key
   ```
2. Check secret path matches expected format: `{environment}/{service_name}/{key}`
3. Verify Vault token has read permissions
4. Check Vault connection status in service logs
5. Ensure you're querying with correct `environment` and `service_name` parameters

### Issue: Vault connection timeout

**Symptoms:**
- Service logs show connection timeout errors
- `vault_enabled: false` in status endpoint

**Solutions:**
1. Check network connectivity to Vault server
2. Verify `VAULT_ADDR` is correct
3. Check firewall rules
4. Ensure Vault server is running

## Vault Client API

The Vault client (`utils/vault_client.py`) provides the following methods:

### `write_secret(environment, service_name, key, value, metadata=None)`
Write a secret to Vault.

**Parameters:**
- `environment`: Environment name (e.g., "production")
- `service_name`: Service name (e.g., "asr-service")
- `key`: Configuration key
- `value`: Secret value to store
- `metadata`: Optional metadata dictionary

**Returns:** `bool` - True if successful

### `read_secret(environment, service_name, key)`
Read a secret from Vault.

**Parameters:**
- `environment`: Environment name
- `service_name`: Service name
- `key`: Configuration key

**Returns:** `str | None` - Secret value or None if not found

### `delete_secret(environment, service_name, key)`
Delete a secret from Vault.

**Parameters:**
- `environment`: Environment name
- `service_name`: Service name
- `key`: Configuration key

**Returns:** `bool` - True if successful

### `list_secrets(environment, service_name=None)`
List secrets in Vault for a given environment.

**Parameters:**
- `environment`: Environment name
- `service_name`: Optional service name filter

**Returns:** `list` - List of secret paths

### `is_connected()`
Check if Vault client is connected and authenticated.

**Returns:** `bool` - True if connected

## Migration Guide

### Migrating Existing Configs to Vault

If you have existing configs stored in PostgreSQL (from previous implementation):

1. **Enable Vault integration** (set environment variables)

2. **Migrate existing configs** to Vault:
   ```bash
   # Get existing config from PostgreSQL
   curl "http://localhost:8082/api/v1/config/my_key?environment=production&service_name=my-service"
   
   # Recreate it in Vault (this will store it in Vault)
   curl -X POST "http://localhost:8082/api/v1/config" \
     -H 'Content-Type: application/json' \
     -d '{
       "key": "my_key",
       "value": "<same-value>",
       "environment": "production",
       "service_name": "my-service",
       "is_encrypted": false
     }'
   ```

3. **Verify migration**:
   ```bash
   # Check Vault has the value
   vault kv get secret/production/my-service/my_key
   
   # Verify it's no longer in PostgreSQL (should return 404)
   # The config should now exist ONLY in Vault
   ```

## Security Considerations

1. **Token Management:**
   - Never commit Vault tokens to version control
   - Use environment variables or secret management systems
   - Rotate tokens regularly

2. **Network Security:**
   - Use TLS for Vault connections in production
   - Restrict network access to Vault server
   - Use Vault's ACL policies to limit access

3. **Audit Logging:**
   - Enable Vault audit logging
   - Monitor access to sensitive secrets
   - Review audit logs regularly

4. **Secret Rotation:**
   - Implement secret rotation policies
   - Use Vault's dynamic secrets where possible
   - Monitor secret age and usage

## Additional Resources

- [HashiCorp Vault Documentation](https://www.vaultproject.io/docs)
- [Vault KV Secrets Engine](https://www.vaultproject.io/docs/secrets/kv)
- [Vault Authentication Methods](https://www.vaultproject.io/docs/auth)
- [Vault Best Practices](https://www.vaultproject.io/docs/best-practices)

