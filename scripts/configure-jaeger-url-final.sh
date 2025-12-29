#!/bin/bash

# Final script to configure Jaeger URL to open correctly
# This ensures URLs open as http://localhost:16686/trace/{trace_id}
# NOT as http://localhost:5602/app/http://localhost:16686/...

set -e

OPENSEARCH_DASHBOARDS_URL="${OPENSEARCH_DASHBOARDS_URL:-http://localhost:5602}"
INDEX_PATTERN_ID="8c4b5b30-da6b-11f0-913a-495f11fa208b"

echo "Configuring Jaeger URL to open externally..."
echo ""

python3 <<PYTHON_SCRIPT
import json
import urllib.request

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
    field_formats = {}
    if 'fieldFormats' in attributes and attributes['fieldFormats']:
        try:
            field_formats = json.loads(attributes['fieldFormats'])
        except:
            field_formats = {}
    
    # Configure URL formatter
    # The key is that OpenSearch should detect http:// URLs as external
    field_formats['jaeger_trace_url'] = {
        "id": "url",
        "params": {
            "urlTemplate": "{{value}}",
            "labelTemplate": "View Trace in Jaeger"
        }
    }
    
    attributes['fieldFormats'] = json.dumps(field_formats)
    
    # Update
    update_data = {"attributes": attributes}
    update_url = f"{opensearch_dashboards_url}/api/saved_objects/index-pattern/{index_pattern_id}"
    update_req = urllib.request.Request(update_url, method='PUT')
    update_req.add_header('osd-xsrf', 'true')
    update_req.add_header('Content-Type', 'application/json')
    update_req.data = json.dumps(update_data).encode('utf-8')
    
    with urllib.request.urlopen(update_req) as response:
        result = json.loads(response.read())
        print("✅ API configuration updated")
    
    print("")
    print("=" * 70)
    print("MANUAL CONFIGURATION REQUIRED")
    print("=" * 70)
    print("")
    print("OpenSearch Dashboards requires manual UI configuration to properly")
    print("handle external URLs. Follow these steps:")
    print("")
    print("1. Open: http://localhost:5602/app/management/opensearch-dashboards/indexPatterns/patterns/8c4b5b30-da6b-11f0-913a-495f11fa208b")
    print("")
    print("2. Search for: jaeger_trace_url")
    print("")
    print("3. Click the EDIT icon (pencil) next to jaeger_trace_url")
    print("")
    print("4. Configure:")
    print("   Format: URL")
    print("   URL Template: {{value}}")
    print("   Label Template: View Trace in Jaeger")
    print("   ⚠️  'Open link in current tab': MUST BE UNCHECKED")
    print("")
    print("5. Click 'Update field'")
    print("")
    print("6. Go to Discover view")
    print("")
    print("7. Hard refresh browser: Ctrl+Shift+R (or Cmd+Shift+R on Mac)")
    print("")
    print("Expected result:")
    print("   ✅ Clicking link opens: http://localhost:16686/trace/{trace_id}")
    print("   ❌ Should NOT open: http://localhost:5602/app/http://localhost:16686/...")
    print("")
    print("If it still doesn't work after manual configuration,")
    print("this may be a browser or OpenSearch Dashboards limitation.")
    print("You can right-click the link and select 'Open link in new tab'")
    print("")
    
except Exception as e:
    print(f"ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
PYTHON_SCRIPT

