# Vault Quick Start Guide

## 🚀 Quick Setup (5 Minutes)

### 1. Start Vault
```bash
# Start all infrastructure (includes Vault)
./scripts/start-all.sh

# OR just Vault
docker compose up -d vault
```

### 2. Configure Config Service

Edit `services/config-service/.env`:
```bash
VAULT_ADDR=http://vault:8200
VAULT_TOKEN=dev-root-token
VAULT_MOUNT_POINT=secret
VAULT_KV_VERSION=2
```

### 3. Verify Setup
```bash
# Check Vault is running
docker compose exec vault vault status

# Check config service can connect
docker compose logs config-service | grep -i vault
```

---

## 📝 Common Operations

### Create Encrypted Config (Sensitive Data)
```bash
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "api_key",
    "value": "secret_key_123",
    "environment": "production",
    "service_name": "asr-service",
    "is_encrypted": true
  }'
```

### Create Non-Encrypted Config (Public Data)
```bash
curl -X POST http://localhost:8082/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "model_path",
    "value": "/models/asr",
    "environment": "production",
    "service_name": "asr-service",
    "is_encrypted": false
  }'
```

### Get Config
```bash
curl "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service"
```

### Update Config
```bash
curl -X PUT "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service" \
  -H 'Content-Type: application/json' \
  -d '{"value": "new_secret_key", "is_encrypted": true}'
```

### Delete Config
```bash
curl -X DELETE "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service"
```

---

## 🔍 Quick Checks

```bash
# Vault status
docker compose exec vault vault status

# List secrets in Vault
docker compose exec vault vault kv list secret/production

# Get secret directly from Vault
docker compose exec vault vault kv get secret/production/asr-service/api_key

# Config service health
curl http://localhost:8082/health

# All services health
./scripts/health-check-all.sh
```

---

## ⚠️ Important Notes

1. **ALL configs** (encrypted and non-encrypted) are stored in **Vault only**
2. **Encrypted configs** are **never cached** (always fresh from Vault)
3. **Always specify** `environment` and `service_name` in API calls
4. **Path format**: `secret/data/{environment}/{service_name}/{key}`

---

## 🆘 Troubleshooting

**Can't connect to Vault?**
```bash
# Check Vault is running
docker compose ps vault

# Check network
docker compose exec config-service ping vault

# Check token
docker compose exec config-service env | grep VAULT_TOKEN
```

**Config not found?**
```bash
# Verify it exists in Vault
docker compose exec vault vault kv get secret/production/asr-service/api_key

# Check query parameters
curl "http://localhost:8082/api/v1/config/api_key?environment=production&service_name=asr-service"
```

---

## 📚 Full Documentation

See [VAULT_USAGE_GUIDE.md](./VAULT_USAGE_GUIDE.md) for complete documentation.

