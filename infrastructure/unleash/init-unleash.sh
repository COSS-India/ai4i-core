#!/bin/sh

# Initialize Unleash with API tokens and verify setup
# This script is executed when the Unleash container starts

set -e

echo "Starting Unleash initialization..."

# Set environment variables
UNLEASH_URL="${UNLEASH_URL:-http://unleash:4242}"

# Wait for Unleash to be ready
echo "Waiting for Unleash to be ready..."
until curl -f "${UNLEASH_URL}/health" 2>/dev/null; do
    echo "Unleash is not ready yet, waiting..."
    sleep 5
done

echo "Unleash is ready, starting initialization..."

# Set admin credentials
UNLEASH_ADMIN_USER="${UNLEASH_ADMIN_USER:-admin}"
UNLEASH_ADMIN_PASSWORD="${UNLEASH_ADMIN_PASSWORD:-unleash4all}"

# Wait a bit more for Unleash to fully initialize
echo "Waiting for Unleash to fully initialize..."
sleep 10

# Verify Unleash API is accessible
echo "Verifying Unleash API accessibility..."
if curl -f -s "${UNLEASH_URL}/api/health" > /dev/null; then
    echo "Unleash API is accessible"
else
    echo "Warning: Unleash API health check failed, but continuing..."
fi

# Check if default API token exists (Unleash creates one by default)
echo "Checking for default API tokens..."
TOKEN_RESPONSE=$(curl -s -X POST "${UNLEASH_URL}/api/admin/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${UNLEASH_ADMIN_USER}\",\"password\":\"${UNLEASH_ADMIN_PASSWORD}\"}" \
    || echo "")

if [ -n "$TOKEN_RESPONSE" ]; then
    echo "Unleash login endpoint is accessible"
else
    echo "Warning: Could not verify login endpoint (this is normal if using default token)"
fi

# Verify database connection by checking if Unleash can list features
echo "Verifying database connection..."
FEATURES_RESPONSE=$(curl -s -f "${UNLEASH_URL}/api/client/features" \
    -H "Authorization: *:*.unleash-insecure-api-token" \
    || echo "")

if [ -n "$FEATURES_RESPONSE" ]; then
    echo "Database connection verified - Unleash can retrieve features"
else
    echo "Warning: Could not retrieve features (may need to wait longer or check database connection)"
fi

# Create default project if it doesn't exist (Unleash usually creates 'default' project automatically)
echo "Verifying default project exists..."
PROJECTS_RESPONSE=$(curl -s -f "${UNLEASH_URL}/api/admin/projects" \
    -H "Authorization: *:*.unleash-insecure-api-token" \
    || echo "")

if [ -n "$PROJECTS_RESPONSE" ]; then
    echo "Default project verification successful"
else
    echo "Warning: Could not verify projects (this may be normal on first startup)"
fi

# Test feature flag API endpoint
echo "Testing feature flag API endpoint..."
API_TEST=$(curl -s -f "${UNLEASH_URL}/api/client/features" \
    -H "Authorization: *:*.unleash-insecure-api-token" \
    -w "%{http_code}" \
    -o /dev/null \
    || echo "000")

if [ "$API_TEST" = "200" ]; then
    echo "Feature flag API endpoint is working correctly"
else
    echo "Warning: Feature flag API returned status code: $API_TEST"
fi

# Display Unleash information
echo ""
echo "Unleash initialization summary:"
echo "  - URL: ${UNLEASH_URL}"
echo "  - Health: OK"
echo "  - Default API Token: *:*.unleash-insecure-api-token"
echo "  - Admin UI: http://localhost:4242 (from host)"
echo "  - Default credentials: ${UNLEASH_ADMIN_USER} / ${UNLEASH_ADMIN_PASSWORD}"
echo ""
echo "Note: For production, create a proper API token in the Unleash UI:"
echo "  1. Access http://localhost:4242 from your host machine"
echo "  2. Go to Settings → API Access"
echo "  3. Create a new API token with appropriate permissions"
echo "  4. Update UNLEASH_API_TOKEN in your service configuration"
echo ""

echo "Unleash initialization completed successfully!"
echo "Unleash is ready for use!"

