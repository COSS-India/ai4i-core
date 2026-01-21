# OpenSearch RBAC Setup Guide

## Current Status

**Development Mode:** Security is **DISABLED** - OpenSearch RBAC is not active.

**Why?** OpenSearch 2.x requires SSL certificates when security is enabled. For development, we've disabled security so the system works immediately.

## What Has Been Implemented

✅ **RBAC Setup Script:** `setup-rbac.sh` is ready and will create:
- 4 organization-specific roles with DLS filters (irctc_viewer, kisanmitra_viewer, bashadaan_viewer, beml_viewer)
- 1 super admin role (no DLS filter)
- 5 users (one for each organization + super admin)

✅ **Index Template:** Organization field already exists in `index-template.json`

✅ **Docker Compose:** RBAC setup service is configured (currently disabled)

## How RBAC Works

### Document Level Security (DLS)
- Each organization role has a DLS filter: `{"term": {"organization": "<org>"}}`
- Users automatically see only logs where `organization` matches their org
- Super admin sees all logs (no filter)

### Example Flow:
```
1. User logs into OpenSearch Dashboards as "irctc_user"
2. OpenSearch checks user's role: "irctc_viewer"
3. DLS filter automatically applied: organization="irctc"
4. User only sees logs where organization="irctc"
```

## Enabling RBAC in Production

### Step 1: Generate SSL Certificates

OpenSearch 2.x requires SSL certificates when security is enabled. You have two options:

#### Option A: Use OpenSearch Demo Certificates (Quick)
```bash
# The OpenSearch Docker image can auto-generate demo certificates
# This is fine for development/testing, NOT for production
```

#### Option B: Generate Production Certificates (Recommended)
```bash
# Use OpenSearch's security demo installer or generate proper certificates
# See: https://opensearch.org/docs/latest/security-plugin/configuration/generate-certificates/
```

### Step 2: Update opensearch.yml

Edit `infrastructure/opensearch/opensearch.yml`:

```yaml
# Enable security
plugins.security.disabled: false

# Configure SSL (use paths to your certificates)
plugins.security.ssl.http.enabled: true
plugins.security.ssl.http.pemcert_filepath: certs/http.pem
plugins.security.ssl.http.pemkey_filepath: certs/http-key.pem
plugins.security.ssl.http.pemtrustedcas_filepath: certs/root-ca.pem

plugins.security.ssl.transport.enabled: true
plugins.security.ssl.transport.pemcert_filepath: certs/node.pem
plugins.security.ssl.transport.pemkey_filepath: certs/node-key.pem
plugins.security.ssl.transport.pemtrustedcas_filepath: certs/root-ca.pem

# Other security settings
plugins.security.allow_default_init_securityindex: true
plugins.security.restapi.roles_enabled: ["all_access", "security_rest_api_access"]
```

### Step 3: Update docker-compose.yml

1. Mount certificates directory:
```yaml
volumes:
  - opensearch-certs:/usr/share/opensearch/config/certs
```

2. Update OpenSearch Dashboards:
```yaml
environment:
  - DISABLE_SECURITY_DASHBOARDS_PLUGIN=false
  - OPENSEARCH_USERNAME=admin
  - OPENSEARCH_PASSWORD=admin
```

### Step 4: Restart OpenSearch

```bash
docker compose restart opensearch
# Wait for OpenSearch to be healthy
```

### Step 5: Run RBAC Setup Script

```bash
docker compose up opensearch-rbac-setup
```

Or manually:
```bash
docker exec -it ai4v-opensearch-rbac-setup sh /setup-rbac.sh
```

### Step 6: Verify RBAC

1. Login to OpenSearch Dashboards: `http://localhost:5602/opensearch`
2. Use credentials: `irctc_user` / `Irctc123!`
3. Verify you only see logs where `organization="irctc"`
4. Login as `super_admin_user` / `SuperAdmin123!`
5. Verify you see all logs

## Created Users and Roles

### Roles:
- `irctc_viewer` - DLS: `organization="irctc"`
- `kisanmitra_viewer` - DLS: `organization="kisanmitra"`
- `bashadaan_viewer` - DLS: `organization="bashadaan"`
- `beml_viewer` - DLS: `organization="beml"`
- `super_admin` - No DLS (sees all)

### Users:
- `irctc_user` / `Irctc123!`
- `kisanmitra_user` / `Kisanmitra123!`
- `bashadaan_user` / `Bashadaan123!`
- `beml_user` / `Beml123!`
- `super_admin_user` / `SuperAdmin123!`

**⚠️ IMPORTANT:** Change default passwords in production!

## Troubleshooting

### OpenSearch won't start with security enabled
- **Issue:** SSL certificates missing or misconfigured
- **Solution:** Ensure certificates exist and paths in `opensearch.yml` are correct

### RBAC setup script fails
- **Issue:** OpenSearch not ready or security not enabled
- **Solution:** Wait for OpenSearch to be healthy, verify security is enabled

### Users can't login
- **Issue:** Passwords incorrect or users not created
- **Solution:** Check `setup-rbac.sh` logs, verify users exist in OpenSearch

### DLS filters not working
- **Issue:** Organization field missing from logs or incorrect format
- **Solution:** Verify logs have `organization` field, check index template

## Notes

- **Development:** Security is disabled - all users can see all logs
- **Production:** Enable security + SSL + run RBAC setup for proper isolation
- **Organization field:** Must match exactly (case-sensitive: "irctc" not "IRCTC")
- **DLS filters:** Automatically applied - users cannot bypass them

