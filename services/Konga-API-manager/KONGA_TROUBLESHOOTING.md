# Kong Manager (Konga) Troubleshooting Guide

## Issue: Konga Cannot Connect to PostgreSQL

**Problem:** Konga displays "Unknown authenticationOk message type" error and cannot start.

**Root Cause:** Konga uses an outdated PostgreSQL client library (`sails-postgresql`) that doesn't support PostgreSQL 14/15's authentication methods.

## ✅ RESOLVED: PostgreSQL Compatibility Fixed

**Solution Implemented:** Created dedicated PostgreSQL 11 instance for Konga.

- **PostgreSQL 11** includes the `consrc` column that Konga requires
- **Authentication** works correctly with PostgreSQL 11
- **Database schema** initialized successfully
- **Konga UI** is accessible at `http://localhost:8002`

## Current Status

- ✅ **Kong Gateway**: Working perfectly at `http://localhost:8001` (Admin API) and `http://localhost:8000` (Proxy)
- ✅ **Kong Manager (Konga)**: Fully operational at `http://localhost:8002` with PostgreSQL 11

## Solutions

### Option 1: Use Kong Admin API Directly (Recommended)

Kong Admin API provides full functionality for managing Kong:

```bash
# List all services
curl http://localhost:8001/services | jq

# List all routes
curl http://localhost:8001/routes | jq

# List all consumers
curl http://localhost:8001/consumers | jq

# Get service details
curl http://localhost:8001/services/asr-service | jq

# Get consumer API keys
curl http://localhost:8001/consumers/asr-client/key-auth | jq
```

**Admin API Documentation:** https://docs.konghq.com/gateway/latest/admin-api/

### Option 2: Use Alternative Management Tools

1. **Postman / Insomnia**: Import Kong Admin API OpenAPI spec
2. **HTTPie**: `http GET localhost:8001/services`
3. **Kong for Kubernetes Operator UI**: If using Kubernetes
4. **Custom Dashboard**: Build using Kong Admin API

### Option 3: Fix Konga PostgreSQL Compatibility

If you need Konga specifically, try these approaches:

#### 3.1 Use PostgreSQL 12 or Earlier

Update `docker-compose.yml`:

```yaml
postgres-konga:
  image: postgres:12-alpine  # Use PostgreSQL 12
  # ... rest of config
```

#### 3.2 Use Konga Fork with Updated Dependencies

Look for Konga forks on GitHub with updated PostgreSQL client libraries.

#### 3.3 Manual Konga Setup

```bash
# Access Konga container
docker exec -it ai4v-kong-manager sh

# Manually update PostgreSQL client (may break Konga)
# Not recommended unless you know what you're doing
```

## Access Points

- **Kong Admin API**: http://localhost:8001
- **Kong Proxy (Gateway)**: http://localhost:8000
- **Kong Manager (Konga)**: http://localhost:8002 ❌ (Not working)

## Verification

Test Kong functionality:

```bash
# Check Kong status
curl http://localhost:8001/status

# Test API endpoint with authentication
export ASR_API_KEY=$(grep ASR_API_KEY .env | cut -d '=' -f2)
curl http://localhost:8000/api/v1/asr/health -H "X-API-Key: $ASR_API_KEY"
```

## Notes

- Kong Gateway itself is fully functional
- All services, routes, and consumers are properly configured
- API authentication works correctly
- The only limitation is the Konga web UI

## Future Considerations

- Consider using Kong Enterprise (includes native Manager UI)
- Monitor Konga GitHub for PostgreSQL 15 support updates
- Use Kong Admin API programmatically for automation

