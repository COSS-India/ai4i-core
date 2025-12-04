# Architecture Migration Guide

## New Architecture: Frontend → Kong → Auth Service → Backend Services

### Overview
This document describes the migration from the old architecture (Frontend → Kong → API Gateway → Backend) to the new architecture (Frontend → Kong → Auth Service → Backend).

### Key Changes

1. **Kong as Single Entry Point**: All frontend requests go through Kong
2. **Token Validation via Auth Service**: Kong validates tokens by calling Auth Service's `/api/v1/auth/validate` endpoint
3. **Direct Backend Routing**: Kong routes directly to backend services, bypassing API Gateway Service
4. **X-API-Key Injection**: Kong automatically injects service-specific X-API-Key headers based on route
5. **Backend Services**: No authentication checks - assume token is validated by Kong

### Implementation Steps

#### Step 1: Create Custom Kong Plugin for Token Validation

Since Kong's `pre-function` plugin doesn't have direct HTTP client access, we need to create a custom plugin.

Create file: `services/Konga-API-manager/plugins/token-validator/kong/plugins/token-validator/handler.lua`

```lua
local http = require "resty.http"
local cjson = require "cjson"

local TokenValidator = {}

TokenValidator.PRIORITY = 1000
TokenValidator.VERSION = "1.0.0"

function TokenValidator:access(conf)
  -- Skip validation for public endpoints
  local path = kong.request.get_path()
  if string.match(path, "^/api/v1/auth/(login|register|refresh|reset%-password|request%-password%-reset|oauth2)") then
    return
  end
  
  -- Extract token from Authorization header
  local auth_header = kong.request.get_header("Authorization")
  if not auth_header or not string.match(auth_header, "^Bearer%s+(.+)$") then
    kong.response.exit(401, { message = "Missing or invalid Authorization header" }, {
      ["WWW-Authenticate"] = "Bearer",
      ["Content-Type"] = "application/json"
    })
  end
  
  local token = string.match(auth_header, "^Bearer%s+(.+)$")
  
  -- Validate token via auth-service
  local httpc = http.new()
  httpc:set_timeout(5000)
  
  local auth_service_url = conf.auth_service_url or "http://ai4v-auth-service:8081/api/v1/auth/validate"
  
  local res, err = httpc:request_uri(auth_service_url, {
    method = "POST",
    headers = {
      ["Authorization"] = "Bearer " .. token,
      ["Content-Type"] = "application/json"
    }
  })
  
  if err then
    kong.log.err("Auth service validation error: ", err)
    kong.response.exit(503, { message = "Authentication service unavailable" }, {
      ["Content-Type"] = "application/json"
    })
  end
  
  if res.status ~= 200 then
    kong.log.warn("Token validation failed with status: ", res.status)
    kong.response.exit(401, { message = "Invalid or expired token" }, {
      ["WWW-Authenticate"] = "Bearer",
      ["Content-Type"] = "application/json"
    })
  end
  
  -- Token is valid, continue
  kong.log.debug("Token validated successfully")
  
  -- Inject X-API-Key if configured
  if conf.api_key then
    kong.service.request.set_header("X-API-Key", conf.api_key)
  end
end

return TokenValidator
```

Create file: `services/Konga-API-manager/plugins/token-validator/kong/plugins/token-validator/schema.lua`

```lua
return {
  name = "token-validator",
  fields = {
    { config = {
        type = "record",
        fields = {
          { auth_service_url = { type = "string", default = "http://ai4v-auth-service:8081/api/v1/auth/validate" } },
          { api_key = { type = "string", default = nil } },
        }
      }
    }
  }
}
```

#### Step 2: Update Kong Dockerfile to Include Plugin

Update `services/Konga-API-manager/Dockerfile` (if exists) or add plugin mounting in `docker-compose.yml`:

```yaml
kong:
  volumes:
    - ./services/Konga-API-manager/kong.yml:/kong/kong.yml:ro
    - ./services/Konga-API-manager/plugins:/usr/local/share/lua/5.1/kong/plugins:ro
```

#### Step 3: Update Kong Configuration

Use the new `kong-new-architecture.yml` file which:
- Routes directly to backend services
- Uses token-validator plugin for authentication
- Injects X-API-Key headers automatically

#### Step 4: Update Frontend

Update `frontend/simple-ui/src/services/api.ts`:
- Change `NEXT_PUBLIC_API_URL` to point to Kong (already done: `http://localhost:8000`)
- Ensure `Authorization: Bearer <token>` header is sent (already done)

#### Step 5: Remove Auth Checks from Backend Services

For each backend service (ASR, TTS, NMT, etc.):
- Remove authentication middleware
- Remove token validation logic
- Services should only handle business logic

#### Step 6: Update Auth Service

Ensure `/api/v1/auth/validate` endpoint:
- Accepts `POST` method (currently accepts GET)
- Returns 200 with user info if valid
- Returns 401 if invalid

### Alternative: Using Kong's HTTP Request Plugin

If custom plugins are not feasible, we can use Kong's `http-request` plugin (if available) or use a simpler approach with `pre-function` and `kong.service.request` to proxy through a validation service.

### Testing

1. Test token validation: Send request with invalid token → should get 401
2. Test token validation: Send request with valid token → should succeed
3. Test X-API-Key injection: Check backend service receives correct X-API-Key
4. Test direct routing: Verify requests go directly to backend, not through API Gateway

### Rollback Plan

Keep the old `kong.yml` file as backup. To rollback:
1. Stop Kong
2. Replace `kong-new-architecture.yml` with old `kong.yml`
3. Restart Kong

