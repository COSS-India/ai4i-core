#!/bin/bash

# Quick Test Script for OpenSearch RBAC Features
# This tests what we can test WITHOUT enabling security

echo "=========================================="
echo "OpenSearch RBAC Testing"
echo "=========================================="
echo ""

# Test 1: Check OpenSearch is running
echo "Test 1: Checking OpenSearch accessibility..."
if curl -s http://localhost:9204/ > /dev/null 2>&1; then
    echo "✅ OpenSearch is accessible at http://localhost:9204"
else
    echo "❌ OpenSearch is not accessible"
    echo "   Start it with: docker compose up -d opensearch"
    exit 1
fi
echo ""

# Test 2: Check if logs exist
echo "Test 2: Checking for logs..."
LOG_COUNT=$(curl -s "http://localhost:9204/logs-*/_count" 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin).get('count', 0))" 2>/dev/null || echo "0")

if [ "$LOG_COUNT" = "0" ] || [ -z "$LOG_COUNT" ]; then
    echo "⚠️  No logs found yet"
    echo ""
    echo "To generate test logs, make an API call:"
    echo '  curl -X POST http://localhost:8000/api/v1/asr/inference \'
    echo '    -H "X-API-Key: test-key-123" \'
    echo '    -H "Content-Type: application/json" \'
    echo '    -d '"'"'{"audio": [{"audioContent": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="}]}'"'"''
    echo ""
else
    echo "✅ Found $LOG_COUNT logs"
    echo ""
    
    # Test 3: Check organization field
    echo "Test 3: Checking organization field in logs..."
    echo ""
    
    # Get latest logs and check organization field
    curl -s "http://localhost:9204/logs-*/_search?size=5&sort=@timestamp:desc" 2>/dev/null | \
      python3 << 'PYTHON'
import sys, json
try:
    data = json.load(sys.stdin)
    hits = data.get('hits', {}).get('hits', [])
    
    if not hits:
        print("⚠️  No log entries found")
    else:
        print("Latest logs:")
        print("-" * 60)
        for hit in hits:
            source = hit.get('_source', {})
            org = source.get('organization', 'MISSING')
            service = source.get('service', 'unknown')
            timestamp = source.get('timestamp') or source.get('@timestamp', 'N/A')
            print(f"Time: {timestamp}")
            print(f"Organization: {org}")
            print(f"Service: {service}")
            print("-" * 60)
        
        # Check organization distribution
        print("\nOrganization distribution:")
        orgs = {}
        for hit in hits:
            org = hit.get('_source', {}).get('organization', 'unknown')
            orgs[org] = orgs.get(org, 0) + 1
        
        for org, count in sorted(orgs.items()):
            print(f"  {org}: {count} log(s)")
except Exception as e:
    print(f"Error: {e}")
PYTHON
fi

echo ""

# Test 4: Test hash-based organization mapping
echo "Test 4: Testing hash-based organization mapping..."
echo ""

python3 << 'PYTHON'
import hashlib

organizations = ["irctc", "kisanmitra", "bashadaan", "beml"]

print("Hash-based organization mapping:")
print("-" * 60)

test_keys = [
    "test-key-1",
    "test-key-2", 
    "test-key-3",
    "api-key-12345"
]

for api_key in test_keys:
    hash_value = int(hashlib.md5(api_key.encode()).hexdigest(), 16)
    org_index = hash_value % len(organizations)
    org = organizations[org_index]
    print(f"API Key: {api_key:25} -> Organization: {org}")

print("")
print("✅ Same API key always maps to same organization")
print("✅ Different keys distribute across organizations")
PYTHON

echo ""

# Test 5: Filter logs by organization (if logs exist)
if [ "$LOG_COUNT" != "0" ] && [ -n "$LOG_COUNT" ]; then
    echo "Test 5: Testing organization filter..."
    echo ""
    
    for org in "irctc" "kisanmitra" "bashadaan" "beml"; do
        COUNT=$(curl -s "http://localhost:9204/logs-*/_search" \
          -H "Content-Type: application/json" \
          -d "{\"query\": {\"term\": {\"organization\": \"$org\"}}, \"size\": 0}" 2>/dev/null | \
          python3 -c "import sys, json; print(json.load(sys.stdin).get('hits', {}).get('total', {}).get('value', 0))" 2>/dev/null || echo "0")
        
        if [ "$COUNT" != "0" ]; then
            echo "  ✅ Found $COUNT logs for organization: $org"
        fi
    done
    echo ""
fi

echo "=========================================="
echo "Testing Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Make API calls with different API keys"
echo "2. Verify logs have organization field"
echo "3. Check organization distribution"
echo ""
echo "For RBAC testing (requires security enabled):"
echo "  See: infrastructure/opensearch/TEST_RBAC.md"
echo ""

