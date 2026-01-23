#!/bin/sh

# OpenSearch RBAC Setup Script
# 
# This script sets up Role-Based Access Control (RBAC) for OpenSearch.
# It creates:
# 1. Organization-specific roles with Document Level Security (DLS) filters
# 2. Users for each organization
# 3. Super admin role and user
#
# DLS filters ensure users can only see logs from their organization.
# Example: irctc_user can only see logs where organization="irctc"

set -e

# Configuration
# Use HTTP (SSL disabled for HTTP interface to allow Fluent Bit connection)
# Can be overridden via environment variable
OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
MAX_RETRIES=30
RETRY_DELAY=2

# Default admin credentials (used for initial setup - demo certificates use admin/admin)
ADMIN_USER="${OPENSEARCH_ADMIN_USER:-admin}"
ADMIN_PASSWORD="${OPENSEARCH_ADMIN_PASSWORD:-admin}"

# SSL verification (not needed for HTTP, but keep for backward compatibility)
INSECURE="${OPENSEARCH_INSECURE:-true}"
# Check if URL uses HTTPS
if echo "$OPENSEARCH_URL" | grep -q "^https://"; then
    CURL_OPTS="-k"  # -k flag skips SSL certificate verification (for demo certs)
    if [ "$INSECURE" != "true" ]; then
        CURL_OPTS=""
    fi
else
    CURL_OPTS=""  # No SSL options needed for HTTP
fi

# Organizations (must match the organizations used in hash-based extraction)
# Using space-separated list instead of array for sh compatibility
ORGANIZATIONS="irctc kisanmitra bashadaan beml"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=========================================="
echo "OpenSearch RBAC Setup"
echo "=========================================="
echo ""

# Function: Wait for OpenSearch to be ready
# This checks if OpenSearch is responding to requests
wait_for_opensearch() {
    echo "Waiting for OpenSearch to be ready..."
    for i in $(seq 1 $MAX_RETRIES); do
        # Try to connect to OpenSearch with basic auth (security enabled)
        # Use appropriate curl options based on HTTP/HTTPS
        if curl -sf $CURL_OPTS -u "${ADMIN_USER}:${ADMIN_PASSWORD}" "${OPENSEARCH_URL}/_cluster/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ OpenSearch is ready!${NC}"
            return 0
        fi
        
        # Also try without auth (in case security isn't fully initialized yet)
        if curl -sf $CURL_OPTS "${OPENSEARCH_URL}/_cluster/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ OpenSearch is ready (no auth required yet)${NC}"
            return 0
        fi
        
        if [ $i -eq $MAX_RETRIES ]; then
            echo -e "${RED}❌ ERROR: OpenSearch did not become ready after $((MAX_RETRIES * RETRY_DELAY)) seconds${NC}"
            exit 1
        fi
        
        echo "  Attempt $i/$MAX_RETRIES: Waiting for OpenSearch..."
        sleep $RETRY_DELAY
    done
}

# Function: Make authenticated request to OpenSearch
# This handles both authenticated and non-authenticated requests
opensearch_request() {
    local method=$1
    local endpoint=$2
    local data=$3
    
    local url="${OPENSEARCH_URL}${endpoint}"
    local response
    
    # Use appropriate curl options based on HTTP/HTTPS
    # Always use authentication when security is enabled
    if [ -n "$data" ]; then
        response=$(curl -s $CURL_OPTS -w "\n%{http_code}" -X "$method" "$url" \
            -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
            -H "Content-Type: application/json" \
            -d "$data" 2>/dev/null || \
        curl -s $CURL_OPTS -w "\n%{http_code}" -X "$method" "$url" \
            -H "Content-Type: application/json" \
            -d "$data" 2>/dev/null)
    else
        response=$(curl -s $CURL_OPTS -w "\n%{http_code}" -X "$method" "$url" \
            -u "${ADMIN_USER}:${ADMIN_PASSWORD}" 2>/dev/null || \
        curl -s $CURL_OPTS -w "\n%{http_code}" -X "$method" "$url" 2>/dev/null)
    fi
    
    echo "$response"
}

# Function: Create role with Document Level Security (DLS) filter
# DLS filter automatically filters documents based on organization field
# Example: {"term": {"organization": "irctc"}} means only show logs where organization="irctc"
create_role_with_dls() {
    local role_name=$1
    local organization=$2
    
    echo "Creating role: ${role_name} (organization: ${organization})"
    
    # Document Level Security (DLS) query
    # This filter ensures users with this role can only see documents where organization field matches
    # DLS must be a JSON string (not a JSON object) in OpenSearch 2.x
    # Escape quotes properly for JSON string
    local dls_query="{\\\"term\\\": {\\\"organization\\\": \\\"${organization}\\\"}}"
    
    # Role definition JSON - use single line to avoid issues with heredoc and curl
    # - cluster_permissions: Required for OpenSearch Dashboards to function
    #   - cluster_composite_ops: Needed for composite operations in Dashboards
    #   - cluster_monitor: Needed to check cluster health and status
    # - index_permissions: What index-level actions are allowed
    #   - index_patterns: Which indices this role can access
    #     - logs-*: Log indices with DLS filter (only see their org's logs)
    #     - .opensearch_dashboards*: Dashboards system indices (needed to use Dashboards UI)
    #   - dls: Document Level Security filter (only for logs-*, not for Dashboards indices)
    #   - allowed_actions: What actions are allowed (read, search, etc.)
    # Add cluster permissions that Dashboards needs:
    # - cluster_composite_ops: For composite operations
    # - cluster_monitor: For cluster health checks
    # - cluster:admin/opendistro/ism/policy/search: For Index State Management (required by Dashboards)
    # - cluster:admin/opensearch/ql/datasources/read: For QL datasources (required by Dashboards)
    # Index permissions for logs-* need monitor permissions for Dashboards to resolve index patterns
    # - indices:monitor/settings/get: Allows Dashboards to get index settings via _cat/indices
    # - indices:monitor/stats: Allows Dashboards to get index statistics via _cat/indices
    # These are required for Dashboards to list and resolve index patterns
    # Dashboards needs indices:data/read/get for reading individual saved objects documents
    # The 'manage' action should include this, but explicitly adding it ensures compatibility
    local role_json="{\"cluster_permissions\":[\"cluster_composite_ops\",\"cluster_monitor\",\"cluster:admin/opendistro/ism/policy/search\",\"cluster:admin/opensearch/ql/datasources/read\"],\"index_permissions\":[{\"index_patterns\":[\"logs-*\"],\"dls\":\"${dls_query}\",\"allowed_actions\":[\"read\",\"indices:data/read/*\",\"indices:admin/mappings/get\",\"indices:admin/get\",\"indices:monitor/settings/get\",\"indices:monitor/stats\"]},{\"index_patterns\":[\".opensearch_dashboards*\",\".kibana*\"],\"dls\":\"\",\"allowed_actions\":[\"read\",\"indices:data/read/*\",\"indices:data/read/get\",\"indices:data/write/*\",\"index\",\"delete\",\"manage\"]}],\"tenant_permissions\":[{\"tenant_patterns\":[\"__user__\"],\"allowed_actions\":[\"kibana_all_write\",\"kibana_all_read\"]}]}"
    
    # Create role via OpenSearch REST API (OpenSearch 2.x uses /_plugins/_security/api, not /_plugins/_security/api)
    local response=$(opensearch_request "PUT" "/_plugins/_security/api/roles/${role_name}" "$role_json")
    local http_code=$(echo "$response" | tail -n1)
    local response_body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
        echo -e "  ${GREEN}✅ Role '${role_name}' created successfully${NC}"
        return 0
    elif echo "$response_body" | grep -q "already exists"; then
        echo -e "  ${YELLOW}⚠️  Role '${role_name}' already exists, updating...${NC}"
        # Try to update existing role
        local update_response=$(opensearch_request "PUT" "/_plugins/_security/api/roles/${role_name}" "$role_json")
        local update_code=$(echo "$update_response" | tail -n1)
        if [ "$update_code" -eq 200 ] || [ "$update_code" -eq 201 ]; then
            echo -e "  ${GREEN}✅ Role '${role_name}' updated successfully${NC}"
            return 0
        else
            echo -e "  ${RED}❌ Failed to update role '${role_name}'. HTTP $update_code${NC}"
            echo "$update_response" | sed '$d'
            return 1
        fi
    else
        echo -e "  ${RED}❌ Failed to create role '${role_name}'. HTTP $http_code${NC}"
        echo "$response_body"
        return 1
    fi
}

# Function: Create super admin role (no DLS filter - can see all logs)
# This role has no Document Level Security filter, so it can see all documents
create_super_admin_role() {
    local role_name="super_admin"
    
    echo "Creating role: ${role_name} (no DLS filter - sees all logs)"
    
    # Super admin role definition
    # - No DLS filter means it can see all documents
    # - Has all_access cluster permission (can manage cluster)
    # - Has all actions on all indices
    local role_json=$(cat <<EOF
{
  "cluster_permissions": ["cluster_all"],
  "index_permissions": [
    {
      "index_patterns": ["*"],
      "allowed_actions": ["*"]
    }
  ]
}
EOF
)
    
    local response=$(opensearch_request "PUT" "/_plugins/_security/api/roles/${role_name}" "$role_json")
    local http_code=$(echo "$response" | tail -n1)
    local response_body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
        echo -e "  ${GREEN}✅ Role '${role_name}' created successfully${NC}"
        return 0
    elif echo "$response_body" | grep -q "already exists"; then
        echo -e "  ${YELLOW}⚠️  Role '${role_name}' already exists, updating...${NC}"
        local update_response=$(opensearch_request "PUT" "/_plugins/_security/api/roles/${role_name}" "$role_json")
        local update_code=$(echo "$update_response" | tail -n1)
        if [ "$update_code" -eq 200 ] || [ "$update_code" -eq 201 ]; then
            echo -e "  ${GREEN}✅ Role '${role_name}' updated successfully${NC}"
            return 0
        else
            echo -e "  ${RED}❌ Failed to update role '${role_name}'. HTTP $update_code${NC}"
            return 1
        fi
    else
        echo -e "  ${RED}❌ Failed to create role '${role_name}'. HTTP $http_code${NC}"
        echo "$response_body"
        return 1
    fi
}

# Function: Create user and assign role
# Creates a user with password and assigns them to a role
create_user() {
    local username=$1
    local password=$2
    local role_name=$3
    
    echo "Creating user: ${username} (role: ${role_name})"
    
    # User definition JSON
    # - password: User's password (in production, use secure password management)
    # - opendistro_security_roles: List of roles assigned to this user
    local user_json=$(cat <<EOF
{
  "password": "${password}",
  "opendistro_security_roles": ["${role_name}"]
}
EOF
)
    
    local response=$(opensearch_request "PUT" "/_plugins/_security/api/internalusers/${username}" "$user_json")
    local http_code=$(echo "$response" | tail -n1)
    local response_body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
        echo -e "  ${GREEN}✅ User '${username}' created successfully${NC}"
        return 0
    elif echo "$response_body" | grep -q "already exists"; then
        echo -e "  ${YELLOW}⚠️  User '${username}' already exists, updating...${NC}"
        local update_response=$(opensearch_request "PUT" "/_plugins/_security/api/internalusers/${username}" "$user_json")
        local update_code=$(echo "$update_response" | tail -n1)
        if [ "$update_code" -eq 200 ] || [ "$update_code" -eq 201 ]; then
            echo -e "  ${GREEN}✅ User '${username}' updated successfully${NC}"
            return 0
        else
            echo -e "  ${RED}❌ Failed to update user '${username}'. HTTP $update_code${NC}"
            return 1
        fi
    else
        echo -e "  ${RED}❌ Failed to create user '${username}'. HTTP $http_code${NC}"
        echo "$response_body"
        return 1
    fi
}

# Main execution
echo "Step 1: Waiting for OpenSearch..."
wait_for_opensearch
echo ""

echo "Step 2: Creating organization-specific roles with DLS filters..."
# Create a role for each organization
# Each role has a DLS filter that only shows logs from that organization
for org in $ORGANIZATIONS; do
    role_name="${org}_viewer"
    create_role_with_dls "$role_name" "$org"
done
echo ""

echo "Step 3: Creating super admin role (no DLS filter)..."
create_super_admin_role
echo ""

# Helper function to capitalize first letter (sh-compatible)
# Used for creating passwords: irctc -> Irctc
capitalize() {
    echo "$1" | awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}'
}

echo "Step 4: Creating users and assigning roles..."
# Create users for each organization
# Each user gets a default password (should be changed in production)
for org in $ORGANIZATIONS; do
    username="${org}_user"
    # Capitalize first letter: Irctc123!@, Kisanmitra123!@, etc.
    org_capitalized=$(capitalize "$org")
    password="${org_capitalized}123!@"
    role_name="${org}_viewer"
    create_user "$username" "$password" "$role_name"
done
echo ""

echo "Step 5: Creating super admin user..."
create_user "super_admin_user" "SuperAdmin123!@" "super_admin"
echo ""

echo "Step 6: Verifying setup..."
# Verify roles exist
echo "Checking roles..."
for org in $ORGANIZATIONS; do
    role_name="${org}_viewer"
    response=$(opensearch_request "GET" "/_plugins/_security/api/roles/${role_name}")
    http_code=$(echo "$response" | tail -n1)
    if [ "$http_code" -eq 200 ]; then
        echo -e "  ${GREEN}✅ Role '${role_name}' verified${NC}"
    else
        echo -e "  ${RED}❌ Role '${role_name}' not found${NC}"
    fi
done

response=$(opensearch_request "GET" "/_plugins/_security/api/roles/super_admin")
http_code=$(echo "$response" | tail -n1)
if [ "$http_code" -eq 200 ]; then
    echo -e "  ${GREEN}✅ Role 'super_admin' verified${NC}"
else
    echo -e "  ${RED}❌ Role 'super_admin' not found${NC}"
fi
echo ""

echo "=========================================="
echo -e "${GREEN}RBAC Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Created roles:"
for org in $ORGANIZATIONS; do
    echo "  - ${org}_viewer (DLS filter: organization=\"${org}\")"
done
echo "  - super_admin (no DLS filter - sees all logs)"
echo ""
echo "Created users:"
for org in $ORGANIZATIONS; do
    org_capitalized=$(capitalize "$org")
    echo "  - ${org}_user (password: ${org_capitalized}123!@)"
done
echo "  - super_admin_user (password: SuperAdmin123!@)"
echo ""
echo "Usage:"
echo "  - Login to OpenSearch Dashboards with organization user (e.g., irctc_user)"
echo "  - User will only see logs where organization matches their org"
echo "  - Super admin can see all logs"
echo ""
echo "⚠️  IMPORTANT: Change default passwords in production!"
echo ""
