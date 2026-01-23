#!/bin/bash

# OpenSearch Initialization Script
# This script ensures the index template is created/updated when OpenSearch starts
# This prevents mapping conflicts that cause logs to fail indexing

set -e

OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
TEMPLATE_NAME="logs-template"
TEMPLATE_FILE="${TEMPLATE_FILE:-/index-template.json}"
MAX_RETRIES=30
RETRY_DELAY=2

# Default admin credentials (for demo setup)
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

echo "=========================================="
echo "OpenSearch Index Template Initialization"
echo "=========================================="
echo ""

# Wait for OpenSearch to be ready
echo "Waiting for OpenSearch to be ready..."
for i in $(seq 1 $MAX_RETRIES); do
    # Try to connect to OpenSearch with basic auth (security enabled)
    # Use appropriate curl options based on HTTP/HTTPS
    if curl -sf $CURL_OPTS -u "${ADMIN_USER}:${ADMIN_PASSWORD}" "$OPENSEARCH_URL/_cluster/health" > /dev/null 2>&1; then
        echo "✅ OpenSearch is ready!"
        break
    fi
    
    # Also try without auth (in case security isn't fully initialized yet)
    if curl -sf $CURL_OPTS "$OPENSEARCH_URL/_cluster/health" > /dev/null 2>&1; then
        echo "✅ OpenSearch is ready (no auth required yet)"
        break
    fi
    
    if [ $i -eq $MAX_RETRIES ]; then
        echo "❌ ERROR: OpenSearch did not become ready after $((MAX_RETRIES * RETRY_DELAY)) seconds"
        exit 1
    fi
    echo "  Attempt $i/$MAX_RETRIES: Waiting for OpenSearch..."
    sleep $RETRY_DELAY
done

echo ""

# Check if template file exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "❌ ERROR: Template file not found at $TEMPLATE_FILE"
    exit 1
fi

echo "Template file found: $TEMPLATE_FILE"
echo ""

# Apply the index template
echo "Applying index template '$TEMPLATE_NAME'..."
# Use appropriate curl options based on HTTP/HTTPS
# Always use authentication when security is enabled
TEMPLATE_RESPONSE=$(curl -s $CURL_OPTS -w "\n%{http_code}" -X PUT "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" \
    -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
    -H "Content-Type: application/json" \
    -d @"$TEMPLATE_FILE" 2>/dev/null || \
    curl -s $CURL_OPTS -w "\n%{http_code}" -X PUT "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" \
    -H "Content-Type: application/json" \
    -d @"$TEMPLATE_FILE" 2>/dev/null)

HTTP_CODE=$(echo "$TEMPLATE_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$TEMPLATE_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ]; then
    echo "✅ Index template '$TEMPLATE_NAME' applied successfully!"
    echo ""
    echo "Template details:"
    echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
elif [ "$HTTP_CODE" -eq 400 ]; then
    # Template might already exist with different content, try to update it
    echo "⚠️  Template exists, attempting to update..."
    UPDATE_RESPONSE=$(curl -s $CURL_OPTS -w "\n%{http_code}" -X PUT "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" \
        -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
        -H "Content-Type: application/json" \
        -d @"$TEMPLATE_FILE" 2>/dev/null || \
        curl -s $CURL_OPTS -w "\n%{http_code}" -X PUT "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" \
        -H "Content-Type: application/json" \
        -d @"$TEMPLATE_FILE" 2>/dev/null)
    UPDATE_CODE=$(echo "$UPDATE_RESPONSE" | tail -n1)
    if [ "$UPDATE_CODE" -eq 200 ] || [ "$UPDATE_CODE" -eq 201 ]; then
        echo "✅ Index template '$TEMPLATE_NAME' updated successfully!"
    else
        echo "❌ ERROR: Failed to update template. HTTP $UPDATE_CODE"
        echo "$UPDATE_RESPONSE" | sed '$d'
        exit 1
    fi
else
    echo "❌ ERROR: Failed to apply template. HTTP $HTTP_CODE"
    echo "$RESPONSE_BODY"
    exit 1
fi

echo ""

# Verify the template was created
echo "Verifying template exists..."
VERIFY_RESPONSE=$(curl -s $CURL_OPTS -u "${ADMIN_USER}:${ADMIN_PASSWORD}" "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" 2>/dev/null || \
    curl -s $CURL_OPTS "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" 2>/dev/null)
if echo "$VERIFY_RESPONSE" | grep -q "\"$TEMPLATE_NAME\""; then
    echo "✅ Template verification successful!"
else
    echo "⚠️  Warning: Could not verify template (this might be OK if OpenSearch version differs)"
fi

echo ""
echo "=========================================="
echo "Initialization Complete!"
echo "=========================================="
echo ""
echo "The index template ensures all 'logs-*' indices will have:"
echo "  - Correct field mappings (service as keyword, not object)"
echo "  - Proper data types for all fields"
echo "  - No mapping conflicts when new indices are created"
echo ""
echo "New indices will automatically use this template."
echo ""

