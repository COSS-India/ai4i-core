#!/bin/sh

# Script to enable RBAC locally for testing
# This generates demo certificates and enables security

set -e

echo "=========================================="
echo "Enabling OpenSearch RBAC for Local Testing"
echo "=========================================="
echo ""

CONTAINER_NAME="ai4v-opensearch"

# Check if container is running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "❌ ERROR: OpenSearch container '$CONTAINER_NAME' is not running"
    echo "Start it with: docker compose up -d opensearch"
    exit 1
fi

echo "Step 1: Stopping OpenSearch..."
docker compose stop opensearch

echo ""
echo "Step 2: Temporarily removing opensearch.yml mount to allow demo installer..."
# We need to let the demo installer modify opensearch.yml
# So we'll temporarily remove our mount, let installer run, then restore

echo ""
echo "Step 3: Starting OpenSearch without our config mount..."
# Start with default config so demo installer can run
docker run -d --name opensearch-temp \
    -e "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m" \
    -e "DISABLE_INSTALL_DEMO_CONFIG=false" \
    opensearchproject/opensearch:2.11.0

echo "Waiting for OpenSearch to generate demo certificates..."
sleep 30

echo ""
echo "Step 4: Copying generated certificates..."
docker exec opensearch-temp mkdir -p /usr/share/opensearch/config/certs
docker exec opensearch-temp /usr/share/opensearch/plugins/opensearch-security/tools/install_demo_configuration.sh -y -i -c

# Copy certificates to host
mkdir -p infrastructure/opensearch/certs
docker cp opensearch-temp:/usr/share/opensearch/config/certs/. infrastructure/opensearch/certs/

echo ""
echo "Step 5: Cleaning up temporary container..."
docker stop opensearch-temp
docker rm opensearch-temp

echo ""
echo "Step 6: Updating opensearch.yml to enable security..."
# Update config file
cat > infrastructure/opensearch/opensearch.yml << 'EOF'
cluster.name: docker-cluster
network.host: 0.0.0.0
discovery.type: single-node

# Enable security plugin for RBAC (local testing with demo certificates)
plugins.security.disabled: false
plugins.security.allow_default_init_securityindex: true
plugins.security.authcz.admin_dn: []
plugins.security.check_snapshot_restore_write_privileges: true
plugins.security.enable_snapshot_restore_privilege: true
plugins.security.restapi.roles_enabled: ["all_access", "security_rest_api_access"]
plugins.security.system_indices.enabled: true
plugins.security.system_indices.indices: [".plugins-ml-config", ".plugins-ml-connector", ".plugins-ml-model-group", ".plugins-ml-model", ".plugins-ml-task", ".opensearch-observability", ".opensearch-observability-log", ".opensearch-observability-traces"]

# SSL Configuration - Using demo certificates (for local testing only)
plugins.security.ssl.http.enabled: true
plugins.security.ssl.http.pemcert_filepath: certs/http.pem
plugins.security.ssl.http.pemkey_filepath: certs/http-key.pem
plugins.security.ssl.http.pemtrustedcas_filepath: certs/root-ca.pem
plugins.security.ssl.transport.enabled: true
plugins.security.ssl.transport.pemcert_filepath: certs/node.pem
plugins.security.ssl.transport.pemkey_filepath: certs/node-key.pem
plugins.security.ssl.transport.pemtrustedcas_filepath: certs/root-ca.pem
plugins.security.ssl.transport.enforce_hostname_verification: false
plugins.security.ssl.transport.resolve_hostname: false
EOF

echo ""
echo "Step 7: Updating docker-compose.yml to mount certificates..."
# This will be done manually or we can update it

echo ""
echo "✅ Demo certificates generated!"
echo ""
echo "Next steps:"
echo "1. Update docker-compose.yml to mount certs directory"
echo "2. Restart OpenSearch: docker compose restart opensearch"
echo "3. Run RBAC setup: docker compose up opensearch-rbac-setup"
echo "4. Update Dashboards config for authentication"
echo ""

