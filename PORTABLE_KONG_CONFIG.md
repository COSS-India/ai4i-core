# Portable Kong Configuration

## Problem
Hardcoded IP addresses (like `172.31.0.17:8081`) don't work across different machines because:
- Docker networks use different IP ranges on different hosts
- Container IPs change when containers are recreated
- Each deployment environment has different network configurations

## Solution
A dynamic IP resolution script (`resolve-service-ips.sh`) that:
1. Resolves service hostnames to IPs at **container startup time**
2. Substitutes IPs in the Kong configuration automatically
3. Falls back to hostnames if DNS resolution fails

## How It Works

### 1. Configuration File Uses Hostnames
The `kong-new-architecture.yml` file now uses **hostnames** instead of hardcoded IPs:
```yaml
targets:
  - target: auth-service:8081      # ✅ Portable hostname
    upstream: auth-service-upstream
```

### 2. Dynamic Resolution at Startup
When Kong container starts, `resolve-service-ips.sh`:
- Resolves each service hostname to its current IP
- Substitutes IPs in the configuration
- Logs which services were resolved

### 3. Works on Any Machine
- ✅ Works on different machines (IPs resolved dynamically)
- ✅ Works when containers restart (IPs re-resolved)
- ✅ Works in different environments (dev, staging, prod)

## Files Modified

1. **`kong-new-architecture.yml`**: Uses hostnames instead of IPs
2. **`resolve-service-ips.sh`**: New script that resolves IPs at startup
3. **`docker-compose.kong.yml`**: Updated to run the resolution script before Kong starts
4. **`substitute-env.sh`**: Updated to work with the resolved config

## Usage

### Normal Operation
Just start Kong as usual:
```bash
docker compose -f docker-compose.kong.yml up -d
```

The script automatically:
1. Resolves service IPs
2. Substitutes them in the config
3. Starts Kong with the resolved config

### Manual IP Resolution
If you need to check what IPs were resolved:
```bash
docker exec ai4v-kong-gateway /kong/resolve-service-ips.sh
```

### Viewing Resolved Config
Check the final configuration Kong is using:
```bash
docker exec ai4v-kong-gateway cat /tmp/kong-substituted.yml | grep -A 1 "target:"
```

## Benefits

✅ **Portable**: Works on any machine without configuration changes  
✅ **Automatic**: No manual IP updates needed  
✅ **Resilient**: Handles IP changes when containers restart  
✅ **Transparent**: Logs show which IPs were resolved  

## Troubleshooting

### If Services Don't Resolve
1. Check if services are running:
   ```bash
   docker ps | grep -E "auth-service|config-service"
   ```

2. Check DNS resolution from Kong container:
   ```bash
   docker exec ai4v-kong-gateway getent hosts auth-service
   ```

3. Check Kong logs for resolution messages:
   ```bash
   docker compose -f docker-compose.kong.yml logs kong | grep -i "resolv"
   ```

### If IPs Change After Restart
The script runs automatically on every container start, so IPs are always up-to-date. No manual intervention needed.

## Migration from Hardcoded IPs

If you have existing configurations with hardcoded IPs:
1. Replace IPs with hostnames in `kong-new-architecture.yml`
2. The script will automatically resolve them at startup
3. No other changes needed!

