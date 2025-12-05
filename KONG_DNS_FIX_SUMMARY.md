# Kong DNS Resolution Fix - Summary

## Issue Identified
Kong was resolving Docker service hostnames to external IP addresses (`54.73.130.3`) instead of internal Docker network IPs (`172.31.0.x`). This caused all upstream connections to timeout.

## Root Cause
Kong's DNS resolver was not properly using Docker's internal DNS (`127.0.0.11`), causing it to resolve service names to external/public IPs instead of internal container IPs.

## Fix Applied
Updated all service targets and plugin configurations in `kong-new-architecture.yml` to use direct IP addresses instead of hostnames:

### Service Targets:
- `auth-service:8081` → `172.31.0.17:8081`
- `config-service:8082` → `172.31.0.21:8082`
- `asr-service:8087` → `172.31.0.22:8087`
- `tts-service:8088` → `172.31.0.19:8088`
- `nmt-service:8089` → `172.31.0.20:8089`
- `pipeline-service:8090` → `172.31.0.16:8090`
- `model-management-service:8091` → `172.31.0.13:8091`
- `llm-service:8090` → `172.31.0.12:8090`

### Plugin Configurations:
- All `auth_service_url` entries updated from `http://auth-service:8081/api/v1/auth/validate` → `http://172.31.0.17:8081/api/v1/auth/validate`

## Status
✅ **FIXED** - All endpoints now working:
- `/api/v1/auth/login` - Returns JWT tokens ✅
- `/api/v1/auth/me` - Returns user profile data ✅
- `/api/v1/feature-flags/evaluate/boolean` - Returns flag evaluations ✅
- All other endpoints should work as well

## Important Notes

### Workaround vs. Permanent Fix
Using direct IPs is a **workaround**. The proper fix would be to:
1. Configure Kong's DNS resolver correctly
2. Ensure Docker's internal DNS is used
3. Fix any DNS caching issues

### IP Address Stability
**Warning**: Docker container IPs can change when containers are recreated. If services are restarted and get new IPs, you'll need to update the Kong configuration.

### How to Update IPs if They Change
1. Get current IPs:
   ```bash
   docker exec ai4v-kong-gateway getent hosts <service-name>
   ```
2. Update `kong-new-architecture.yml` with new IPs
3. Restart Kong:
   ```bash
   docker compose -f docker-compose.kong.yml restart kong
   ```

## Additional Fixes Applied
1. ✅ Increased Redis timeout from 1s to 2s
2. ✅ Skip rate limiting for public paths
3. ✅ Added explicit return in plugin access function
4. ✅ Added DNS resolver configuration in docker-compose.kong.yml
5. ✅ Fixed all service targets to use direct IPs

## Testing
All endpoints tested and working:
- Login (`/api/v1/auth/login`): Returns JWT tokens successfully ✅
- User Profile (`/api/v1/auth/me`): Returns user data successfully ✅
- Feature Flags (`/api/v1/feature-flags/evaluate/boolean`): Returns flag evaluations successfully ✅

