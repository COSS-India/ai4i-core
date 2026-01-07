#!/bin/bash
 
# Final fix for making jaeger_trace_url clickable in OpenSearch Dashboards
 
OPENSEARCH_DASHBOARDS_URL="${OPENSEARCH_DASHBOARDS_URL:-http://localhost:5602}"
INDEX_PATTERN_TITLE="${INDEX_PATTERN_TITLE:-logs-*}"

echo "=========================================="
echo "Jaeger URL Link Fix Script"
echo "=========================================="
echo ""
echo "Step 1: Checking OpenSearch Dashboards..."
echo "----------------------------------------"

# Check if OpenSearch Dashboards is accessible
if ! curl -sf "$OPENSEARCH_DASHBOARDS_URL/api/status" > /dev/null 2>&1; then
    echo "❌ ERROR: Cannot connect to OpenSearch Dashboards at $OPENSEARCH_DASHBOARDS_URL"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check if OpenSearch Dashboards is running:"
    echo "     docker compose ps opensearch-dashboards"
    echo ""
    echo "  2. Start it if needed:"
    echo "     docker compose up -d opensearch-dashboards"
    echo ""
    echo "  3. Wait 30-60 seconds for it to start, then retry"
    exit 1
fi
echo "✅ OpenSearch Dashboards is accessible"
echo ""

echo "Step 2: Finding index pattern ID for '$INDEX_PATTERN_TITLE'..."
echo "----------------------------------------"

# Auto-discover the index pattern ID
INDEX_PATTERN_ID=$(curl -sf -H "osd-xsrf: true" \
  "$OPENSEARCH_DASHBOARDS_URL/api/saved_objects/_find?type=index-pattern&search_fields=title&search=$INDEX_PATTERN_TITLE" 2>/dev/null | \
  python3 -c "import sys, json; data=json.load(sys.stdin); print(data['saved_objects'][0]['id'] if data.get('saved_objects') and len(data['saved_objects']) > 0 else '')" 2>/dev/null)

if [ -z "$INDEX_PATTERN_ID" ]; then
    echo "❌ ERROR: Index pattern '$INDEX_PATTERN_TITLE' not found"
    echo ""
    echo "Available index patterns:"
    curl -sf -H "osd-xsrf: true" \
      "$OPENSEARCH_DASHBOARDS_URL/api/saved_objects/_find?type=index-pattern&per_page=100" 2>/dev/null | \
      python3 -c "import sys, json; data=json.load(sys.stdin); [print(f\"  - {obj['attributes']['title']} (ID: {obj['id']})\") for obj in data.get('saved_objects', [])]" 2>/dev/null
    echo ""
    echo "To create the index pattern:"
    echo "  1. Go to $OPENSEARCH_DASHBOARDS_URL"
    echo "  2. Navigate to Management → Index Patterns"
    echo "  3. Create index pattern: '$INDEX_PATTERN_TITLE'"
    echo "  4. Set time field: @timestamp"
    echo ""
    echo "Or use API:"
    echo "  curl -X POST '$OPENSEARCH_DASHBOARDS_URL/api/saved_objects/index-pattern/logs-pattern' \\"
    echo "    -H 'osd-xsrf: true' -H 'Content-Type: application/json' \\"
    echo "    -d '{\"attributes\":{\"title\":\"$INDEX_PATTERN_TITLE\",\"timeFieldName\":\"@timestamp\"}}'"
    exit 1
fi

echo "✅ Found index pattern: $INDEX_PATTERN_TITLE"
echo "   Pattern ID: $INDEX_PATTERN_ID"
echo ""

echo "Step 3: Configuring jaeger_trace_url field format..."
echo "----------------------------------------"

python3 <<PYTHON_SCRIPT
import json
import sys
import urllib.request
import urllib.error
 
opensearch_dashboards_url = "$OPENSEARCH_DASHBOARDS_URL"
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
    
    # Configure jaeger_trace_url with explicit external link settings
    field_formats['jaeger_trace_url'] = {
        "id": "url",
        "params": {
            "urlTemplate": "{{value}}",
            "labelTemplate": "View Trace in Jaeger",
            "openLinkInCurrentTab": False
        }
    }
    
    # Also try configuring the .keyword version
    field_formats['jaeger_trace_url.keyword'] = {
        "id": "url",
        "params": {
            "urlTemplate": "{{value}}",
            "labelTemplate": "View Trace in Jaeger",
            "openLinkInCurrentTab": False
        }
    }
    
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
        print("✅ Configuration updated successfully")
        print(f"   Pattern ID: {result.get('id', index_pattern_id)}")
        print("")
        print("Next steps:")
        print("   1. Clear browser cache completely:")
        print("      - Press Ctrl+Shift+Delete")
        print("      - Select 'Cached images and files'")
        print("      - Click 'Clear data'")
        print("")
        print("   2. OR use Incognito/Private window:")
        print("      - Open new incognito window")
        print("      - Go to OpenSearch Dashboards")
        print("")
        print("   3. In Discover view:")
        print("      - Remove jaeger_trace_url from table (click X)")
        print("      - Add it back (click +)")
        print("      - Hard refresh: Ctrl+Shift+R")
        print("")
        print("   4. If still not working, try using 'jaeger_trace_url.keyword' field instead")
    
except urllib.error.HTTPError as e:
    print(f"❌ HTTP Error {e.code}: {e.reason}")
    if e.code == 404:
        print("")
        print("The index pattern was found in step 2 but is now missing.")
        print("This might be a timing issue or the pattern was deleted.")
        print("")
        print("Please recreate the index pattern and try again.")
    sys.exit(1)
except Exception as e:
    print(f"❌ ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_SCRIPT

echo ""
echo "=========================================="
echo "Configuration Complete!"
echo "=========================================="