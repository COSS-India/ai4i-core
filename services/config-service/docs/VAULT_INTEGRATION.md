# Vault Integration Guide

## Overview

The Configuration Management Service integrates with HashiCorp Vault to securely store and manage encrypted configurations. When a configuration is marked as `is_encrypted=True`, the actual sensitive value is stored in Vault, while metadata and audit information remain in PostgreSQL.

## Architecture

### Storage Strategy

- **Encrypted Configurations** (`is_encrypted=True`):
  - **Actual value**: Stored in HashiCorp Vault
  - **Metadata**: Stored in PostgreSQL (key, environment, service_name, version, timestamps)
  - **Placeholder**: PostgreSQL stores `VAULT_STORED` as the value field

- **Non-Encrypted Configurations** (`is_encrypted=False`):
  - **Value**: Stored directly in PostgreSQL
  - **Caching**: Cached in Redis for performance

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

- **Transparent Storage**: When creating/updating a config with `is_encrypted=True`, the value is automatically stored in Vault
- **Automatic Retrieval**: When fetching encrypted configs, values are automatically retrieved from Vault
- **Graceful Fallback**: If Vault is unavailable, encrypted configs fall back to PostgreSQL (with warnings)
- **No Caching**: Encrypted values are never cached in Redis for security reasons
- **Automatic Cleanup**: When deleting encrypted configs, both Vault and PostgreSQL entries are removed

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
2. Metadata is stored in PostgreSQL with value field set to `VAULT_STORED`
3. Response returns the actual value from Vault

### Retrieving an Encrypted Configuration

```bash
curl "http://localhost:8082/api/v1/config/database_password?environment=production&service_name=auth-service"
```

**What happens:**
1. Metadata is retrieved from PostgreSQL
2. If `is_encrypted=True` and value is `VAULT_STORED`, the actual value is fetched from Vault
3. Response includes the actual decrypted value

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
2. PostgreSQL metadata is updated (version incremented, timestamp updated)
3. History entry is created in PostgreSQL

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
1. Value is deleted from Vault
2. Actual value is stored in PostgreSQL
3. `is_encrypted` flag is updated

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
1. Value is stored in Vault
2. PostgreSQL value is set to `VAULT_STORED`
3. `is_encrypted` flag is updated

### Deleting an Encrypted Configuration

```bash
curl -X DELETE "http://localhost:8082/api/v1/config/database_password?environment=production&service_name=auth-service"
```

**What happens:**
1. Value is deleted from Vault
2. Metadata is deleted from PostgreSQL
3. History entries remain for audit purposes

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

**Note:** The response always returns the actual value, even for encrypted configs.

### Get Configuration

**Request:**
```
GET /api/v1/config/secret_key?environment=production&service_name=my-service
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

**Note:** For encrypted configs, the value is fetched from Vault on every request (not cached).

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

**Note:** For encrypted configs in the list, values are fetched from Vault.

## Error Handling

### Vault Connection Failures

If Vault is unavailable or authentication fails:

1. **During Creation/Update:**
   - Warning is logged
   - Value is stored in PostgreSQL instead (not recommended for sensitive data)
   - Service continues to operate

2. **During Retrieval:**
   - If value is marked as `VAULT_STORED` but Vault is unavailable:
     - Warning is logged
     - Placeholder value is returned
     - Service continues to operate

3. **Service Status:**
   - Check `/api/v1/config/status` endpoint
   - `vault_enabled` field indicates Vault connection status

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

### Issue: Encrypted configs not storing in Vault

**Symptoms:**
- Configs with `is_encrypted=True` are stored in PostgreSQL instead
- Logs show "Failed to write encrypted config to Vault"

**Solutions:**
1. Check `VAULT_ADDR` is correct
2. Verify `VAULT_TOKEN` is valid and has proper permissions
3. Ensure KV secrets engine is enabled at the mount point
4. Check Vault server is running and accessible

### Issue: Cannot retrieve encrypted config values

**Symptoms:**
- API returns `VAULT_STORED` instead of actual value
- Logs show "Secret not found in Vault"

**Solutions:**
1. Verify secret exists in Vault:
   ```bash
   vault kv get secret/production/my-service/my_key
   ```
2. Check secret path matches expected format
3. Verify Vault token has read permissions
4. Check Vault connection status in service logs

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

### Migrating Existing Encrypted Configs to Vault

If you have existing encrypted configs stored in PostgreSQL:

1. **Enable Vault integration** (set environment variables)

2. **Update existing configs** to trigger Vault storage:
   ```bash
   # Get existing encrypted config
   curl "http://localhost:8082/api/v1/config/my_key?environment=production&service_name=my-service"
   
   # Update it (this will move it to Vault)
   curl -X PUT "http://localhost:8082/api/v1/config/my_key?environment=production&service_name=my-service" \
     -H 'Content-Type: application/json' \
     -d '{
       "value": "<same-value>",
       "is_encrypted": true
     }'
   ```

3. **Verify migration**:
   ```bash
   # Check PostgreSQL has VAULT_STORED placeholder
   # Check Vault has the actual value
   vault kv get secret/production/my-service/my_key
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

