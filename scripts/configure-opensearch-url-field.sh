#!/bin/bash

# Script to configure OpenSearch Dashboards to make jaeger_trace_url field clickable
# This configures the field formatter for the jaeger_trace_url field in the logs* index pattern
# Note: Only jaeger_trace_url is configured (no duplicate fields like jaeger_url, jaeger_trace_id)

set -e

OPENSEARCH_DASHBOARDS_URL="${OPENSEARCH_DASHBOARDS_URL:-http://localhost:5602}"
OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9204}"

echo "Configuring OpenSearch Dashboards to make jaeger_trace_url clickable..."
echo "OpenSearch Dashboards URL: $OPENSEARCH_DASHBOARDS_URL"
echo ""

# Wait for OpenSearch Dashboards to be ready
echo "Waiting for OpenSearch Dashboards to be ready..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -s -f "$OPENSEARCH_DASHBOARDS_URL/api/status" > /dev/null 2>&1; then
        echo "OpenSearch Dashboards is ready!"
        break
    fi
    attempt=$((attempt + 1))
    echo "Attempt $attempt/$max_attempts: Waiting for OpenSearch Dashboards..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "ERROR: OpenSearch Dashboards is not responding. Please check if it's running."
    exit 1
fi

# Get the index pattern ID for logs*
echo "Finding index pattern for logs*..."
INDEX_PATTERN_RESPONSE=$(curl -s "$OPENSEARCH_DASHBOARDS_URL/api/saved_objects/_find?type=index-pattern&search_fields=title&search=logs*" || echo "")

if [ -z "$INDEX_PATTERN_RESPONSE" ] || [ "$INDEX_PATTERN_RESPONSE" = "{}" ]; then
    echo "ERROR: Could not find index pattern 'logs*'. Please create it first in OpenSearch Dashboards:"
    echo "  1. Go to Stack Management > Index Patterns"
    echo "  2. Create index pattern: logs*"
    echo "  3. Time field: @timestamp"
    exit 1
fi

# Extract the index pattern ID (try to parse JSON, fallback to grep)
INDEX_PATTERN_ID=$(echo "$INDEX_PATTERN_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")

if [ -z "$INDEX_PATTERN_ID" ]; then
    # Try alternative parsing
    INDEX_PATTERN_ID=$(echo "$INDEX_PATTERN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['saved_objects'][0]['id'] if data.get('saved_objects') else '')" 2>/dev/null || echo "")
fi

if [ -z "$INDEX_PATTERN_ID" ]; then
    echo "ERROR: Could not extract index pattern ID. Response:"
    echo "$INDEX_PATTERN_RESPONSE"
    echo ""
    echo "Please manually configure the field formatter:"
    echo "  1. Go to Stack Management > Index Patterns"
    echo "  2. Click on 'logs*' index pattern"
    echo "  3. Find 'jaeger_trace_url' field"
    echo "  4. Click the edit icon (pencil)"
    echo "  5. Set Format to 'URL'"
    echo "  6. Set URL Template to: {{value}}"
    echo "  7. Set Label Template to: View Trace"
    exit 1
fi

echo "Found index pattern ID: $INDEX_PATTERN_ID"

# Get the current index pattern configuration
echo "Fetching current index pattern configuration..."
INDEX_PATTERN_CONFIG=$(curl -s "$OPENSEARCH_DASHBOARDS_URL/api/saved_objects/index-pattern/$INDEX_PATTERN_ID" || echo "")

if [ -z "$INDEX_PATTERN_CONFIG" ]; then
    echo "ERROR: Could not fetch index pattern configuration"
    exit 1
fi

# Update the field formatter for jaeger_trace_url
# We need to add/update the fieldFormats in the index pattern attributes
echo "Configuring jaeger_trace_url field formatter..."

# Create the update payload with URL formatter
UPDATE_PAYLOAD=$(cat <<EOF
{
  "attributes": {
    "fieldFormats": "{\"jaeger_trace_url\":{\"id\":\"url\",\"params\":{\"urlTemplate\":\"{{value}}\",\"labelTemplate\":\"View Trace in Jaeger\"}}}"
  }
}
EOF
)

# Try to update (this might require the full attributes object, so we'll use a Python script instead)
echo "Attempting to update field formatter via API..."

# Use Python to properly merge the fieldFormats
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
    
    # Get current attributes
    attributes = data.get('attributes', {})
    
    # Parse or initialize fieldFormats
    field_formats = {}
    if 'fieldFormats' in attributes and attributes['fieldFormats']:
        try:
            field_formats = json.loads(attributes['fieldFormats'])
        except:
            field_formats = {}
    
    # Configure jaeger_trace_url formatter with URL template
    # jaeger_trace_url field now contains only the trace_id
    # URL template constructs: http://localhost:16686/trace/{trace_id}
    # This ensures OpenSearch Dashboards treats it as external absolute URL
    field_formats['jaeger_trace_url'] = {
        "id": "url",
        "params": {
            # Base URL + trace_id value from the field
            # {{value}} will be replaced with the trace_id stored in jaeger_trace_url
            "urlTemplate": "http://localhost:16686/trace/{{value}}",
            "labelTemplate": "View Trace in Jaeger"
        }
    }
    
    # Update attributes
    attributes['fieldFormats'] = json.dumps(field_formats)
    
    # Prepare update payload
    update_data = {
        "attributes": attributes
    }
    
    # Send update request
    update_url = f"{opensearch_dashboards_url}/api/saved_objects/index-pattern/{index_pattern_id}"
    update_req = urllib.request.Request(update_url, method='PUT')
    update_req.add_header('osd-xsrf', 'true')
    update_req.add_header('Content-Type', 'application/json')
    update_req.data = json.dumps(update_data).encode('utf-8')
    
    with urllib.request.urlopen(update_req) as response:
        result = json.loads(response.read())
        print("SUCCESS: Field formatter configured!")
        print(f"Updated index pattern: {result.get('id', index_pattern_id)}")
        sys.exit(0)
        
except urllib.error.HTTPError as e:
    error_body = e.read().decode('utf-8')
    print(f"ERROR: HTTP {e.code}")
    print(f"Response: {error_body}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {str(e)}")
    sys.exit(1)
PYTHON_SCRIPT

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Configuration complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Refresh your OpenSearch Dashboards browser page"
    echo "  2. Go to Discover view"
    echo "  3. The jaeger_trace_url field should now be clickable"
    echo ""
    echo "If it's still not clickable, try:"
    echo "  1. Go to Stack Management > Index Patterns"
    echo "  2. Click on 'logs*' index pattern"
    echo "  3. Refresh field list (click 'Refresh' button)"
    echo "  4. Find 'jaeger_trace_url' field and verify it shows 'URL' format"
else
    echo ""
    echo "⚠️  Automatic configuration failed. Please configure manually:"
    echo ""
    echo "Manual Configuration Steps:"
    echo "  1. Open OpenSearch Dashboards: $OPENSEARCH_DASHBOARDS_URL"
    echo "  2. Go to: Stack Management > Index Patterns"
    echo "  3. Click on the 'logs*' index pattern"
    echo "  4. Scroll down to find 'jaeger_trace_url' field"
    echo "  5. Click the edit icon (pencil) next to the field"
    echo "  6. Set the following:"
    echo "     - Format: URL"
    echo "     - URL Template: {{value}}"
    echo "     - Label Template: View Trace in Jaeger"
    echo "  7. Click 'Update field'"
    echo "  8. Refresh your Discover view"
fi

