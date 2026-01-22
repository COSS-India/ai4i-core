#!/bin/sh

# Script to create index patterns for each user in OpenSearch Dashboards
# This runs after Dashboards is ready to ensure index patterns are created
# in the correct tenant for each user

set -e

DASHBOARDS_URL="${OPENSEARCH_DASHBOARDS_URL:-http://opensearch-dashboards:5601}"
MAX_RETRIES=60
RETRY_DELAY=5

# Organizations
ORGANIZATIONS="irctc kisanmitra bashadaan beml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "=========================================="
echo "Creating Index Patterns for Users"
echo "=========================================="
echo ""
echo "Using Dashboards URL: ${DASHBOARDS_URL}"
echo ""

# Wait for Dashboards to be ready
# Fixed: Handle authentication - 401 means Dashboards is ready but needs auth (which is fine)
echo "Waiting for OpenSearch Dashboards to be ready..."
for i in $(seq 1 $MAX_RETRIES); do
    # Try to access Dashboards API
    # Extract HTTP code properly - curl outputs code to stderr when using -w, so we capture it correctly
    http_code=$(curl -sk -w "%{http_code}" -o /dev/null "${DASHBOARDS_URL}/opensearch/api/status" 2>&1 | tail -1)
    
    # Debug output
    echo "  Attempt $i/$MAX_RETRIES: HTTP $http_code"
    
    # 200 = ready and accessible
    # 401 = ready but requires authentication (this is expected and means it's working)
    if [ "$http_code" = "200" ] || [ "$http_code" = "401" ]; then
        echo -e "${GREEN}✅ Dashboards is ready! (HTTP $http_code)${NC}"
        break
    fi
    
    if [ $i -eq $MAX_RETRIES ]; then
        echo -e "${RED}❌ ERROR: Dashboards did not become ready after $((MAX_RETRIES * RETRY_DELAY)) seconds${NC}"
        echo "  Last HTTP status code: $http_code"
        echo "  Tried URL: ${DASHBOARDS_URL}/opensearch/api/status"
        exit 1
    fi
    
    sleep $RETRY_DELAY
done
echo ""

# Helper to capitalize first letter
capitalize() {
    echo "$1" | awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}'
}

# Function: Create index pattern for a user
create_index_pattern() {
    local username=$1
    local password=$2
    local pattern_name="logs-*"
    local time_field="@timestamp"
    
    echo "Creating index pattern '${pattern_name}' for user: ${username}"
    
    # Check if index pattern already exists
    # Fixed: Add /opensearch basepath since SERVER_BASEPATH=/opensearch
    local check_response=$(curl -sk -u "${username}:${password}" \
        "${DASHBOARDS_URL}/opensearch/api/saved_objects/_find?type=index-pattern&search_fields=title&search=${pattern_name}" 2>/dev/null || echo "{}")
    
    local existing_count=$(echo "$check_response" | grep -o '"id"' | wc -l || echo "0")
    if [ "$existing_count" -gt 0 ]; then
        echo -e "  ${YELLOW}⚠️  Index pattern '${pattern_name}' already exists for ${username}${NC}"
        return 0
    fi
    
    # Create index pattern via Dashboards Saved Objects API
    local pattern_json=$(cat <<EOF
{
  "attributes": {
    "title": "${pattern_name}",
    "timeFieldName": "${time_field}"
  }
}
EOF
)
    
    # Fixed: Add /opensearch basepath since SERVER_BASEPATH=/opensearch
    local response=$(curl -sk -w "\n%{http_code}" -X POST \
        "${DASHBOARDS_URL}/opensearch/api/saved_objects/index-pattern" \
        -u "${username}:${password}" \
        -H "Content-Type: application/json" \
        -H "osd-xsrf: true" \
        -d "$pattern_json" 2>/dev/null || echo "ERROR\n500")
    
    local http_code=$(echo "$response" | tail -n1)
    local response_body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
        echo -e "  ${GREEN}✅ Index pattern '${pattern_name}' created for ${username}${NC}"
        return 0
    elif echo "$response_body" | grep -qi "already exists\|duplicate"; then
        echo -e "  ${YELLOW}⚠️  Index pattern '${pattern_name}' already exists for ${username}${NC}"
        return 0
    else
        echo -e "  ${RED}❌ Failed to create index pattern for ${username} (HTTP $http_code)${NC}"
        echo "  Response: $response_body"
        return 1
    fi
}
# Create index patterns for each organization user
echo "Creating index patterns for organization users..."
for org in $ORGANIZATIONS; do
    username="${org}_user"
    org_capitalized=$(capitalize "$org")
    password="${org_capitalized}123!@"
    create_index_pattern "$username" "$password"
done
echo ""

# Create index pattern for super admin
echo "Creating index pattern for super admin..."
create_index_pattern "super_admin_user" "SuperAdmin123!@"
echo ""

echo "=========================================="
echo -e "${GREEN}Index Pattern Creation Complete!${NC}"
echo "=========================================="
echo ""
echo "All users now have index patterns configured."
echo "They can access Discover and view their organization's logs."
echo ""