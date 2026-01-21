# Testing OpenSearch RBAC - Step by Step Guide

## Current Status Check

First, let's check if security is enabled:

```bash
# Check OpenSearch security status
curl -s http://localhost:9204/ | jq
```

If you see OpenSearch responding without authentication, security is **disabled** (development mode).

---

## Testing Plan

### Phase 1: Test Current Setup (Without RBAC)

Even without RBAC enabled, we can verify that:
1. Organization field exists in logs
2. Logs are being created with organization tags
3. OpenSearch is working

#### Test 1: Verify Organization Field in Logs

```bash
# Check if logs have organization field
curl -s "http://localhost:9204/logs-*/_search?size=5" | jq '.hits.hits[]._source.organization'
```

**Expected:** Should see organization values like "irctc", "kisanmitra", "bashadaan", "beml", or "unknown"

#### Test 2: Generate Test Logs with Organization

Make an API call with an API key to generate logs:

```bash
# Replace YOUR_API_KEY with an actual API key
curl -X POST http://localhost:8000/api/v1/asr/inference \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "audio": [{
      "audioContent": "base64_encoded_audio_here"
    }]
  }'
```

Then check the log:
```bash
# Check the latest log entry
curl -s "http://localhost:9204/logs-*/_search?sort=@timestamp:desc&size=1" | jq '.hits.hits[0]._source | {organization, service, message}'
```

**Expected:** Should see `organization` field with a value (irctc, kisanmitra, bashadaan, or beml)

#### Test 3: Filter Logs by Organization

```bash
# Get logs for a specific organization
curl -s "http://localhost:9204/logs-*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "term": {
        "organization": "irctc"
      }
    },
    "size": 5
  }' | jq '.hits.hits[]._source | {organization, service, timestamp}'
```

**Expected:** Should only see logs where `organization="irctc"`

---

### Phase 2: Enable RBAC and Test (Production Setup)

⚠️ **Note:** This requires SSL certificates. For quick testing, we can use demo certificates.

#### Step 1: Enable Security with Demo Certificates

The OpenSearch Docker image can auto-generate demo certificates. Let's enable it:

```bash
# First, stop OpenSearch
docker compose stop opensearch

# Update opensearch.yml to enable security
# (We'll do this via script)
```

#### Step 2: Quick Test Script

Create a test script to enable security temporarily:

```bash
# Create test script
cat > /tmp/test-rbac-enable.sh << 'EOF'
#!/bin/bash
# Backup current config
cp infrastructure/opensearch/opensearch.yml infrastructure/opensearch/opensearch.yml.backup

# Enable security (will use demo certs if available)
sed -i 's/plugins.security.disabled: true/plugins.security.disabled: false/' infrastructure/opensearch/opensearch.yml

# Add minimal SSL config (OpenSearch will try to use demo certs)
cat >> infrastructure/opensearch/opensearch.yml << 'YAML'
plugins.security.allow_default_init_securityindex: true
plugins.security.restapi.roles_enabled: ["all_access", "security_rest_api_access"]
YAML

echo "Security enabled. Restart OpenSearch: docker compose restart opensearch"
EOF

chmod +x /tmp/test-rbac-enable.sh
```

**⚠️ Warning:** This might fail if certificates aren't available. OpenSearch 2.x is strict about SSL.

---

## Alternative: Test RBAC Script Without Enabling Security

We can test the RBAC script logic without actually enabling security:

### Test 1: Verify Script Syntax

```bash
# Check script syntax
sh -n infrastructure/opensearch/setup-rbac.sh
echo "Exit code: $?"  # Should be 0 if syntax is correct
```

### Test 2: Test Script Functions (Dry Run)

```bash
# Test the script with dry-run mode (if we add it)
# For now, let's manually test the API calls
```

### Test 3: Test Organization Extraction

Verify that organization extraction works in your API calls:

```bash
# Make API call and check logs
API_KEY="test-key-123"
curl -X POST http://localhost:8000/api/v1/asr/inference \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"audio": [{"audioContent": "dGVzdA=="}]}'

# Wait a moment for logs
sleep 2

# Check what organization was assigned
curl -s "http://localhost:9204/logs-*/_search?sort=@timestamp:desc&size=1" | \
  jq '.hits.hits[0]._source.organization'
```

**Expected:** Should see one of: "irctc", "kisanmitra", "bashadaan", "beml"

---

## Complete Testing Workflow

### Test Scenario 1: Organization in Logs (Current - Works Now)

```bash
#!/bin/bash
echo "=== Test 1: Verify Organization Field in Logs ==="

# Make API call with API key
API_KEY="test-api-key-$(date +%s)"
echo "Using API key: $API_KEY"

curl -X POST http://localhost:8000/api/v1/asr/inference \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "audio": [{
      "audioContent": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
    }]
  }' > /dev/null 2>&1

sleep 3

# Check logs
echo ""
echo "Checking logs..."
curl -s "http://localhost:9204/logs-*/_search?sort=@timestamp:desc&size=5" | \
  jq -r '.hits.hits[] | "\(._source.timestamp // ._source["@timestamp"]) | \(._source.organization // "MISSING") | \(._source.service // "unknown")"'

echo ""
echo "✅ Test complete - Check if organization field is present"
```

### Test Scenario 2: Organization Consistency

```bash
#!/bin/bash
echo "=== Test 2: Verify Same API Key = Same Organization ==="

API_KEY="consistent-test-key-12345"

# Make 3 calls with same API key
for i in {1..3}; do
  echo "Call $i..."
  curl -X POST http://localhost:8000/api/v1/asr/inference \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"audio": [{"audioContent": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="}]}' \
    > /dev/null 2>&1
  sleep 1
done

sleep 3

# Check all logs have same organization
echo ""
echo "Checking organization consistency..."
ORGS=$(curl -s "http://localhost:9204/logs-*/_search?sort=@timestamp:desc&size=3" | \
  jq -r '.hits.hits[]._source.organization' | sort -u)

if [ $(echo "$ORGS" | wc -l) -eq 1 ]; then
  echo "✅ SUCCESS: All logs have same organization: $ORGS"
else
  echo "❌ FAILED: Found multiple organizations:"
  echo "$ORGS"
fi
```

### Test Scenario 3: Different API Keys = Different Organizations

```bash
#!/bin/bash
echo "=== Test 3: Different API Keys Map to Different Organizations ==="

# Use 10 different API keys
for i in {1..10}; do
  API_KEY="test-key-$i-$(date +%s)"
  echo "Testing API key $i..."
  curl -X POST http://localhost:8000/api/v1/asr/inference \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"audio": [{"audioContent": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="}]}' \
    > /dev/null 2>&1
  sleep 0.5
done

sleep 3

# Check organizations
echo ""
echo "Organizations found:"
curl -s "http://localhost:9204/logs-*/_search?sort=@timestamp:desc&size=10" | \
  jq -r '.hits.hits[] | "\(._source.organization // "unknown")"' | \
  sort | uniq -c

echo ""
echo "✅ Should see distribution across: irctc, kisanmitra, bashadaan, beml"
```

---

## Testing RBAC Script (When Security is Enabled)

### Test 1: Run RBAC Setup Script

```bash
# Start RBAC setup container
docker compose up opensearch-rbac-setup

# Check logs
docker logs ai4v-opensearch-rbac-setup
```

**Expected Output:**
```
✅ OpenSearch is ready!
✅ Role 'irctc_viewer' created successfully
✅ Role 'kisanmitra_viewer' created successfully
...
✅ User 'irctc_user' created successfully
...
```

### Test 2: Verify Roles Created

```bash
# List all roles (requires authentication)
curl -u admin:admin -s "http://localhost:9204/_plugins/_security/api/roles" | jq 'keys'
```

**Expected:** Should see: `irctc_viewer`, `kisanmitra_viewer`, `bashadaan_viewer`, `beml_viewer`, `super_admin`

### Test 3: Test User Login

1. Open OpenSearch Dashboards: `http://localhost:5602/opensearch`
2. Login as `irctc_user` / `Irctc123!`
3. Go to Discover
4. Search for logs
5. **Expected:** Should only see logs where `organization="irctc"`

### Test 4: Test Super Admin

1. Login as `super_admin_user` / `SuperAdmin123!`
2. Search for logs
3. **Expected:** Should see ALL logs from all organizations

### Test 5: Test DLS Filter

```bash
# Login as irctc_user and query
curl -u irctc_user:Irctc123! -s "http://localhost:9204/logs-*/_search" | \
  jq '.hits.hits[] | ._source.organization' | sort -u

# Should ONLY return "irctc"
```

---

## Quick Test Commands

### Check if Organization Field Exists

```bash
curl -s "http://localhost:9204/logs-*/_search?size=1" | \
  jq '.hits.hits[0]._source | has("organization")'
```

### Count Logs by Organization

```bash
curl -s "http://localhost:9204/logs-*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "aggs": {
      "by_org": {
        "terms": {
          "field": "organization",
          "size": 10
        }
      }
    }
  }' | jq '.aggregations.by_org.buckets'
```

### Test Hash-Based Organization Mapping

```bash
# Test the hash function (Python)
python3 << 'PYTHON'
import hashlib

organizations = ["irctc", "kisanmitra", "bashadaan", "beml"]

test_keys = ["key1", "key2", "key3", "test-api-key-123"]

for api_key in test_keys:
    hash_value = int(hashlib.md5(api_key.encode()).hexdigest(), 16)
    org_index = hash_value % len(organizations)
    org = organizations[org_index]
    print(f"API Key: {api_key:30} -> Organization: {org}")
PYTHON
```

---

## Troubleshooting Tests

### If logs don't have organization field:

```bash
# Check if middleware is setting organization
docker logs ai4v-api-gateway 2>&1 | grep -i organization | tail -10
```

### If RBAC script fails:

```bash
# Check OpenSearch logs
docker logs ai4v-opensearch 2>&1 | tail -50

# Check if security is enabled
curl -s http://localhost:9204/ | jq '.tagline'
# If it works without auth, security is disabled
```

### If users can't login:

```bash
# Verify users exist (requires auth)
curl -u admin:admin -s "http://localhost:9204/_plugins/_security/api/internalusers" | jq 'keys'
```

---

## Summary: What to Test

### ✅ Can Test Now (Security Disabled):
1. Organization field in logs
2. Organization extraction from API keys
3. Hash-based organization mapping
4. Filtering logs by organization

### ⚠️ Requires Security Enabled:
1. User login to OpenSearch Dashboards
2. DLS filters (automatic filtering)
3. Role-based access
4. Super admin vs org users

---

## Next Steps

1. **Test current setup** - Verify organization field works
2. **Enable security** - When ready for production
3. **Run RBAC setup** - Create roles and users
4. **Test user access** - Verify DLS filters work

Need help with any specific test? Let me know!

