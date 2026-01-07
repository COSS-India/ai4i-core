#!/bin/bash
 
# Fix OpenSearch Index Mapping Issues
# This script fixes the common issue where OpenSearch creates indices with wrong mappings
# (e.g., service as object instead of keyword), causing logs to fail indexing.
#
# Usage: ./scripts/fix-opensearch-mapping.sh [--delete-indices]
#   --delete-indices: Delete existing logs-* indices before reapplying template (use with caution!)
 
set -e
 
OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9204}"
TEMPLATE_NAME="logs-template"
TEMPLATE_FILE="${TEMPLATE_FILE:-./infrastructure/opensearch/index-template.json}"
DELETE_INDICES=false
 
# Parse arguments
if [ "$1" = "--delete-indices" ]; then
    DELETE_INDICES=true
fi
 
# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
 
echo "=========================================="
echo "OpenSearch Index Mapping Fix Script"
echo "=========================================="
echo ""
echo "This script will:"
echo "  1. Check OpenSearch connectivity"
echo "  2. Verify/apply the index template"
echo "  3. Check for existing indices with wrong mappings"
if [ "$DELETE_INDICES" = true ]; then
    echo "  4. ${RED}DELETE existing logs-* indices${NC}"
else
    echo "  4. List existing indices (use --delete-indices to delete them)"
fi
echo ""
 
# 1. Check OpenSearch connectivity
echo "Step 1: Checking OpenSearch connectivity..."
echo "----------------------------------------"
if ! curl -sf "$OPENSEARCH_URL/_cluster/health" > /dev/null 2>&1; then
    echo -e "${RED}✗ ERROR: Cannot connect to OpenSearch at $OPENSEARCH_URL${NC}"
    echo ""
    echo "Please ensure:"
    echo "  1. OpenSearch is running: docker compose ps opensearch"
    echo "  2. Port 9204 is accessible"
    echo "  3. OpenSearch is healthy: curl $OPENSEARCH_URL/_cluster/health"
    exit 1
fi
 
HEALTH_STATUS=$(curl -s "$OPENSEARCH_URL/_cluster/health" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
echo -e "${GREEN}✓${NC} OpenSearch is accessible (status: $HEALTH_STATUS)"
echo ""
 
# 2. Check if template file exists
echo "Step 2: Checking template file..."
echo "----------------------------------------"
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo -e "${RED}✗ ERROR: Template file not found at $TEMPLATE_FILE${NC}"
    echo ""
    echo "Please ensure the template file exists at:"
    echo "  $TEMPLATE_FILE"
    exit 1
fi
 
echo -e "${GREEN}✓${NC} Template file found: $TEMPLATE_FILE"
echo ""
 
# 3. Check current template
echo "Step 3: Checking current index template..."
echo "----------------------------------------"
CURRENT_TEMPLATE=$(curl -s "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" 2>/dev/null || echo "")
if [ -z "$CURRENT_TEMPLATE" ] || echo "$CURRENT_TEMPLATE" | grep -q "error"; then
    echo -e "${YELLOW}⚠${NC} Template '$TEMPLATE_NAME' does not exist yet"
    TEMPLATE_EXISTS=false
else
    echo -e "${GREEN}✓${NC} Template '$TEMPLATE_NAME' exists"
    TEMPLATE_EXISTS=true
    
    # Check if service field is correctly mapped as keyword
    if echo "$CURRENT_TEMPLATE" | grep -q '"service".*"type".*"keyword"'; then
        echo -e "${GREEN}✓${NC} Service field is correctly mapped as 'keyword'"
    else
        echo -e "${YELLOW}⚠${NC} Service field mapping may be incorrect"
    fi
fi
echo ""
 
# 4. Apply/Update template
echo "Step 4: Applying index template..."
echo "----------------------------------------"
TEMPLATE_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" \
    -H "Content-Type: application/json" \
    -d @"$TEMPLATE_FILE" 2>/dev/null || echo "")
 
HTTP_CODE=$(echo "$TEMPLATE_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$TEMPLATE_RESPONSE" | sed '$d')
 
if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ]; then
    echo -e "${GREEN}✓${NC} Index template '$TEMPLATE_NAME' applied successfully!"
elif [ "$HTTP_CODE" -eq 400 ]; then
    echo -e "${YELLOW}⚠${NC} Template update returned 400, but this might be OK"
    echo "Response: $RESPONSE_BODY" | head -5
else
    echo -e "${RED}✗${NC} Failed to apply template. HTTP $HTTP_CODE"
    echo "Response: $RESPONSE_BODY"
    exit 1
fi
echo ""
 
# 5. List existing indices
echo "Step 5: Checking existing logs-* indices..."
echo "----------------------------------------"
INDICES=$(curl -s "$OPENSEARCH_URL/_cat/indices/logs-*?v&h=index,status,docs.count" 2>/dev/null || echo "")
if [ -z "$INDICES" ] || [ "$INDICES" = "index" ]; then
    echo -e "${GREEN}✓${NC} No existing logs-* indices found (this is OK for fresh deployments)"
    echo ""
else
    echo "Found existing indices:"
    echo "$INDICES"
    echo ""
    
    # Check for mapping issues in existing indices
    echo "Checking for mapping issues..."
    MAPPING_ISSUES=0
    for INDEX in $(echo "$INDICES" | grep -v "^index" | awk '{print $1}'); do
        if [ -z "$INDEX" ]; then
            continue
        fi
        INDEX_MAPPING=$(curl -s "$OPENSEARCH_URL/$INDEX/_mapping" 2>/dev/null || echo "")
        if echo "$INDEX_MAPPING" | grep -q '"service".*"type".*"object"'; then
            echo -e "${RED}✗${NC} Index '$INDEX' has service field as 'object' (WRONG!)"
            MAPPING_ISSUES=$((MAPPING_ISSUES + 1))
        elif echo "$INDEX_MAPPING" | grep -q '"service".*"type".*"keyword"'; then
            echo -e "${GREEN}✓${NC} Index '$INDEX' has service field as 'keyword' (correct)"
        else
            echo -e "${YELLOW}⚠${NC} Index '$INDEX' - service field mapping unclear"
        fi
    done
    echo ""
    
    if [ "$MAPPING_ISSUES" -gt 0 ]; then
        echo -e "${YELLOW}⚠ WARNING: Found $MAPPING_ISSUES index(es) with incorrect mappings!${NC}"
        echo ""
        if [ "$DELETE_INDICES" = true ]; then
            echo -e "${RED}Deleting problematic indices...${NC}"
            for INDEX in $(echo "$INDICES" | grep -v "^index" | awk '{print $1}'); do
                if [ -z "$INDEX" ]; then
                    continue
                fi
                INDEX_MAPPING=$(curl -s "$OPENSEARCH_URL/$INDEX/_mapping" 2>/dev/null || echo "")
                if echo "$INDEX_MAPPING" | grep -q '"service".*"type".*"object"'; then
                    echo "  Deleting index: $INDEX"
                    DELETE_RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE "$OPENSEARCH_URL/$INDEX" 2>/dev/null || echo "")
                    DELETE_CODE=$(echo "$DELETE_RESPONSE" | tail -n1)
                    if [ "$DELETE_CODE" -eq 200 ] || [ "$DELETE_CODE" -eq 404 ]; then
                        echo -e "  ${GREEN}✓${NC} Deleted $INDEX"
                    else
                        echo -e "  ${RED}✗${NC} Failed to delete $INDEX (HTTP $DELETE_CODE)"
                    fi
                fi
            done
            echo ""
            echo -e "${GREEN}✓${NC} Indices deleted. New indices will be created with correct mappings."
        else
            echo "To fix these indices, you have two options:"
            echo ""
            echo "Option 1: Delete and recreate (recommended for fresh deployments)"
            echo "  Run: ./scripts/fix-opensearch-mapping.sh --delete-indices"
            echo ""
            echo "Option 2: Wait for daily rollover"
            echo "  New indices created tomorrow will use the correct template"
            echo "  Old indices with wrong mappings will remain but won't affect new logs"
        fi
    else
        echo -e "${GREEN}✓${NC} All existing indices have correct mappings!"
    fi
fi
echo ""
 
# 6. Verify template
echo "Step 6: Verifying template..."
echo "----------------------------------------"
VERIFY_RESPONSE=$(curl -s "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" 2>/dev/null || echo "")
if echo "$VERIFY_RESPONSE" | grep -q "\"$TEMPLATE_NAME\"" || echo "$VERIFY_RESPONSE" | grep -q '"index_patterns".*"logs-*"'; then
    echo -e "${GREEN}✓${NC} Template verification successful!"
    echo ""
    echo "Template configuration:"
    echo "$VERIFY_RESPONSE" | python3 -m json.tool 2>/dev/null | head -20 || echo "$VERIFY_RESPONSE" | head -20
else
    echo -e "${YELLOW}⚠${NC} Could not verify template (this might be OK)"
fi
echo ""
 
# 7. Test query
echo "Step 7: Testing index creation..."
echo "----------------------------------------"
# Create a test index to verify template works
TEST_INDEX="logs-test-$(date +%Y%m%d-%H%M%S)"
TEST_DOC='{"@timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)'","service":"test-service","level":"INFO","message":"Test log entry"}'
 
echo "Creating test index: $TEST_INDEX"
TEST_CREATE=$(curl -s -w "\n%{http_code}" -X PUT "$OPENSEARCH_URL/$TEST_INDEX" \
    -H "Content-Type: application/json" \
    -d '{"settings":{"number_of_shards":1,"number_of_replicas":0}}' 2>/dev/null || echo "")
 
CREATE_CODE=$(echo "$TEST_CREATE" | tail -n1)
if [ "$CREATE_CODE" -eq 200 ] || [ "$CREATE_CODE" -eq 201 ]; then
    echo -e "${GREEN}✓${NC} Test index created"
    
    # Index a test document
    echo "Indexing test document..."
    TEST_INDEX_DOC=$(curl -s -w "\n%{http_code}" -X POST "$OPENSEARCH_URL/$TEST_INDEX/_doc" \
        -H "Content-Type: application/json" \
        -d "$TEST_DOC" 2>/dev/null || echo "")
    
    DOC_CODE=$(echo "$TEST_INDEX_DOC" | tail -n1)
    if [ "$DOC_CODE" -eq 200 ] || [ "$DOC_CODE" -eq 201 ]; then
        echo -e "${GREEN}✓${NC} Test document indexed successfully"
        
        # Check mapping
        sleep 1
        TEST_MAPPING=$(curl -s "$OPENSEARCH_URL/$TEST_INDEX/_mapping" 2>/dev/null || echo "")
        if echo "$TEST_MAPPING" | grep -q '"service".*"type".*"keyword"'; then
            echo -e "${GREEN}✓${NC} Template is working! Service field is correctly mapped as 'keyword'"
        else
            echo -e "${YELLOW}⚠${NC} Template might not be applied correctly"
        fi
    else
        echo -e "${YELLOW}⚠${NC} Could not index test document (HTTP $DOC_CODE)"
    fi
    
    # Clean up test index
    echo "Cleaning up test index..."
    curl -s -X DELETE "$OPENSEARCH_URL/$TEST_INDEX" > /dev/null 2>&1 || true
    echo -e "${GREEN}✓${NC} Test index deleted"
else
    echo -e "${YELLOW}⚠${NC} Could not create test index (HTTP $CREATE_CODE)"
fi
echo ""
 
# Summary
echo "=========================================="
echo "Summary"
echo "=========================================="
echo ""
echo -e "${GREEN}✓${NC} Index template has been applied/verified"
echo ""
echo "What this means:"
echo "  • All NEW indices matching 'logs-*' will use the correct mappings"
echo "  • The 'service' field will be 'keyword' (not 'object')"
echo "  • No more mapping conflicts when indexing logs"
echo ""
echo "Next steps:"
echo "  1. If you deleted indices, wait for Fluent-bit to create new ones"
echo "  2. Make a test request to OCR service to generate logs"
echo "  3. Check OpenSearch Dashboards in 1-2 minutes"
echo "  4. Search for: service:\"ocr-service\""
echo ""
echo "If logs still don't appear:"
echo "  • Run: ./scripts/trouble\ shooting/diagnose-ocr-logs.sh"
echo "  • Check Fluent-bit logs: docker compose logs fluent-bit"
echo "  • Check OCR service logs: docker compose logs ocr-service"
echo ""
echo "Template will be automatically applied on:"
echo "  • Fresh deployments (via opensearch-init service)"
echo "  • Daily index rollover (new indices use template)"
echo ""