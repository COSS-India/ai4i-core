# Kong Integration Review - Findings and Issues

## Overview
Comprehensive review of Kong API Gateway integration for AIV4-Core microservices architecture.

## Current Status
- ✅ Kong is running (version 3.4.2)
- ✅ Plugin structure is correct (handler.lua, schema.lua)
- ✅ Configuration parses successfully
- ✅ Plugin is loaded (`KONG_PLUGINS: token-validator`)
- ❌ Requests are hanging when going through Kong
- ❌ Config-service works directly but not through Kong

## Plugin Structure

### Files Present
1. ✅ `handler.lua` - Plugin logic (261 lines)
2. ✅ `schema.lua` - Configuration schema (108 lines)
3. ❌ `init.lua` - **MISSING** (may not be required for Kong 3.4, but should be checked)

### Plugin Location
- Mounted at: `/usr/local/share/lua/5.1/kong/plugins/token-validator/`
- Files: `handler.lua`, `schema.lua`

## Configuration Review

### Docker Compose Setup
- ✅ Kong service configured in `docker-compose.kong.yml`
- ✅ Plugin mounted correctly
- ✅ Environment variables passed
- ✅ Network: `microservices-network` (external)
- ✅ Config substitution script working

### Kong Configuration (`kong-new-architecture.yml`)
- ✅ Upstreams defined for all services
- ✅ Targets configured (config-service:8082)
- ✅ Services and routes defined
- ✅ Token-validator plugin configured
- ⚠️ Service timeouts set to 60s (may be too high)

### Config Service Route
```yaml
- name: config-service
  url: http://config-service-upstream
  connect_timeout: 60000
  write_timeout: 60000
  read_timeout: 60000
  routes:
    - name: config-route
      paths:
        - /api/v1/config
        - /api/v1/feature-flags
      plugins:
        - name: token-validator
          config:
            enable_rate_limit: false
```

## Issues Identified

### 1. **Rate Limiting Still Being Called (FIXED)**
- **Issue**: Rate limiting function was being called even for public paths
- **Fix Applied**: Skip rate limiting for public paths
- **Status**: ✅ Fixed in handler.lua line 224-228

### 2. **Redis Connection Timeout (FIXED)**
- **Issue**: Redis connection timeout was 1 second, too short
- **Fix Applied**: Increased to 2 seconds
- **Status**: ✅ Fixed in handler.lua line 74

### 3. **Request Hanging - Root Cause Unknown**
- **Issue**: Requests hang when going through Kong, return 499 status
- **Symptoms**: 
  - No requests reach config-service
  - Kong logs show 499 errors
  - Direct access to config-service works fine
- **Possible Causes**:
  1. Plugin blocking request flow
  2. Upstream connection issue
  3. Network routing problem
  4. Missing return statement in plugin

### 4. **Plugin Flow Issue (SUSPECTED)**
- The plugin's `access` phase should allow requests to proceed
- Current code doesn't explicitly return, which should be fine
- But requests are not reaching upstream

## Plugin Code Review

### Handler.lua Analysis

#### Access Phase Flow:
1. ✅ CORS preflight handling (OPTIONS)
2. ✅ Public path detection
3. ✅ Token validation (for protected paths)
4. ✅ Rate limiting (skipped for public paths)
5. ✅ Header injection
6. ❓ **No explicit return** - should allow request to proceed

#### Potential Issues:
- Line 167: Debug logging added (good)
- Line 224-228: Rate limiting skipped for public paths (good)
- **Missing**: Explicit return or error handling if something fails silently

## Network Connectivity

### Verified:
- ✅ Kong can resolve `config-service` DNS (172.31.0.21)
- ✅ Kong can resolve `redis` DNS (172.31.0.2)
- ✅ Both containers on same network
- ❓ Kong → config-service connectivity not tested directly

## Recommendations

### Immediate Actions:
1. **Add explicit return/nil at end of access phase** to ensure request proceeds
2. **Test Kong → config-service connectivity** from within Kong container
3. **Check Kong upstream health status** for config-service
4. **Add more detailed logging** to trace request flow
5. **Verify plugin is not blocking** by temporarily disabling it

### Code Fixes Needed:
1. Add explicit return at end of `access` function
2. Add error handling for edge cases
3. Verify plugin allows request to proceed to upstream

### Testing Steps:
1. Test direct Kong → config-service connection
2. Check Kong admin API for upstream status
3. Monitor Kong error logs during request
4. Test with plugin temporarily disabled
5. Verify network connectivity between containers

## Missing Components

### Files:
- ❓ `init.lua` - May not be required for Kong 3.4, but should verify

### Configuration:
- ✅ All required configs present
- ⚠️ Service timeouts may need adjustment

### Network:
- ✅ Network configuration correct
- ❓ Need to verify actual connectivity

## Latest Findings (After Review)

### ✅ Fixed Issues:
1. **Explicit return added** in access function (line 247)
2. **Rate limiting skipped** for public paths (line 224-228)
3. **Redis timeout increased** to 2 seconds (line 74)
4. **DNS resolution verified** - Kong ↔ config-service works both ways

### ❌ Still Broken:
- Requests still hanging (499 status)
- No requests reaching config-service
- Plugin appears to be working but request not proceeding

### 🔍 Critical Missing Check:
- **Kong upstream health status** - Need to verify if Kong can see config-service as healthy
- **Actual HTTP connectivity** - DNS works but HTTP connection not tested
- **Kong admin API** - Need to check upstream/target status

## Next Steps

1. ✅ **Add explicit return in plugin** - DONE
2. ⏳ **Test upstream connectivity** - Need to test HTTP connection from Kong
3. ⏳ **Check Kong admin API** - Need to verify upstream/target health status
4. ⏳ **Add request tracing** - Need more detailed logging
5. ⏳ **Test with minimal plugin** - Temporarily disable plugin to isolate issue

## Root Cause Hypothesis

The most likely cause is that **Kong cannot establish an HTTP connection to config-service**, even though DNS resolution works. This could be due to:
1. Config-service not listening on the expected interface
2. Firewall/network policy blocking connections
3. Kong upstream health check failing
4. Port mismatch (8082 vs expected port)

## Immediate Action Required

**Test HTTP connectivity from Kong to config-service:**
```bash
docker exec ai4v-kong-gateway sh -c "wget -O- http://config-service:8082/health"
```

If this fails, that's the root cause. If it succeeds, the issue is in Kong's routing/plugin logic.

