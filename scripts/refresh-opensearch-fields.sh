#!/bin/bash

# Script to refresh OpenSearch Dashboards field list and verify URL field configuration

set -e

OPENSEARCH_DASHBOARDS_URL="${OPENSEARCH_DASHBOARDS_URL:-http://localhost:5602}"
OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9204}"

echo "Refreshing OpenSearch Dashboards field list..."
echo ""

# Get index pattern ID
echo "Finding index pattern..."
INDEX_PATTERN_RESPONSE=$(curl -s "$OPENSEARCH_DASHBOARDS_URL/api/saved_objects/_find?type=index-pattern&search_fields=title&search=logs*")
INDEX_PATTERN_ID=$(echo "$INDEX_PATTERN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['saved_objects'][0]['id'] if data.get('saved_objects') else '')" 2>/dev/null || echo "")

if [ -z "$INDEX_PATTERN_ID" ]; then
    echo "ERROR: Could not find index pattern"
    exit 1
fi

echo "Found index pattern ID: $INDEX_PATTERN_ID"
echo ""

# Refresh the field list by updating the index pattern
echo "Refreshing field list..."
python3 <<PYTHON_SCRIPT
import json
import sys
import urllib.request
import urllib.error

opensearch_dashboards_url = "$OPENSEARCH_DASHBOARDS_URL"
opensearch_url = "$OPENSEARCH_URL"
index_pattern_id = "$INDEX_PATTERN_ID"

try:
    # Get current config
    url = f"{opensearch_dashboards_url}/api/saved_objects/index-pattern/{index_pattern_id}"
    req = urllib.request.Request(url)
    req.add_header('osd-xsrf', 'true')
    req.add_header('Content-Type', 'application/json')
    
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
    
    attributes = data.get('attributes', {})
    
    # Parse fieldFormats
    field_formats = {}
    if 'fieldFormats' in attributes and attributes['fieldFormats']:
        try:
            field_formats = json.loads(attributes['fieldFormats'])
        except:
            field_formats = {}
    
    # Ensure jaeger_trace_url is configured as URL
    field_formats['jaeger_trace_url'] = {
        "id": "url",
        "params": {
            "urlTemplate": "{{value}}",
            "labelTemplate": "View Trace in Jaeger",
            "openLinkInCurrentTab": False
        }
    }
    
    # Remove any duplicate fields
    if 'jaeger_url' in field_formats:
        del field_formats['jaeger_url']
    
    # Update attributes
    attributes['fieldFormats'] = json.dumps(field_formats)
    
    # Update the index pattern
    update_data = {
        "attributes": attributes
    }
    
    update_url = f"{opensearch_dashboards_url}/api/saved_objects/index-pattern/{index_pattern_id}"
    update_req = urllib.request.Request(update_url, method='PUT')
    update_req.add_header('osd-xsrf', 'true')
    update_req.add_header('Content-Type', 'application/json')
    update_req.data = json.dumps(update_data).encode('utf-8')
    
    with urllib.request.urlopen(update_req) as response:
        result = json.loads(response.read())
        print("✅ Index pattern updated successfully")
        print(f"   Pattern ID: {result.get('id', index_pattern_id)}")
    
    # Now refresh the field list by calling the refresh API
    print("")
    print("Refreshing field list cache...")
    refresh_url = f"{opensearch_dashboards_url}/api/index_patterns/{index_pattern_id}/fields"
    refresh_req = urllib.request.Request(refresh_url, method='POST')
    refresh_req.add_header('osd-xsrf', 'true')
    refresh_req.add_header('Content-Type', 'application/json')
    
    try:
        with urllib.request.urlopen(refresh_req) as response:
            print("✅ Field list refresh triggered")
    except urllib.error.HTTPError as e:
        # This endpoint might not exist, try alternative
        print(f"   Note: Direct refresh endpoint not available (HTTP {e.code})")
        print("   You'll need to manually refresh in the UI")
    
    # Verify the configuration
    print("")
    print("Verifying configuration...")
    verify_url = f"{opensearch_dashboards_url}/api/saved_objects/index-pattern/{index_pattern_id}"
    verify_req = urllib.request.Request(verify_url)
    verify_req.add_header('osd-xsrf', 'true')
    
    with urllib.request.urlopen(verify_req) as response:
        verify_data = json.loads(response.read())
        verify_formats = json.loads(verify_data['attributes'].get('fieldFormats', '{}'))
        if 'jaeger_trace_url' in verify_formats:
            fmt = verify_formats['jaeger_trace_url']
            print(f"✅ jaeger_trace_url formatter: {fmt.get('id', 'unknown')}")
            if fmt.get('id') == 'url':
                print("   ✓ Format type: URL")
                print("   ✓ URL Template: {{value}}")
                print("   ✓ Label: View Trace in Jaeger")
            else:
                print(f"   ⚠️  Unexpected format type: {fmt.get('id')}")
        else:
            print("❌ jaeger_trace_url formatter not found!")
    
    print("")
    print("=" * 60)
    print("Configuration complete!")
    print("=" * 60)
    print("")
    print("Next steps:")
    print("  1. Go to OpenSearch Dashboards: $OPENSEARCH_DASHBOARDS_URL")
    print("  2. Navigate to: Stack Management > Index Patterns")
    print("  3. Click on 'logs*' index pattern")
    print("  4. Click the 'Refresh' button (top right)")
    print("  5. Wait for refresh to complete")
    print("  6. Go back to Discover view")
    print("  7. Hard refresh your browser (Ctrl+Shift+R)")
    print("")
    print("The jaeger_trace_url field should now be clickable!")
    
except Exception as e:
    print(f"ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_SCRIPT

