#!/bin/bash
# Diagnostic script for OCR logs not appearing in OpenSearch Dashboard
# Usage: ./scripts/diagnose-ocr-logs.sh
 
set -e
 
echo "=========================================="
echo "OCR Logs OpenSearch Diagnostic Tool"
echo "=========================================="
echo ""
 
# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
 
# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
    fi
}
 
# 1. Check OCR Service Environment
echo "1. Checking OCR Service Environment..."
echo "----------------------------------------"
SERVICE_NAME=$(docker compose exec -T ocr-service printenv SERVICE_NAME 2>/dev/null || echo "")
if [ -z "$SERVICE_NAME" ]; then
    print_status 1 "SERVICE_NAME is NOT set in OCR service container"
    echo "   → This is likely the problem! Set SERVICE_NAME=ocr-service"
else
    print_status 0 "SERVICE_NAME is set to: $SERVICE_NAME"
    if [ "$SERVICE_NAME" != "ocr-service" ]; then
        echo -e "   ${YELLOW}⚠ WARNING: SERVICE_NAME should be 'ocr-service' but is '$SERVICE_NAME'${NC}"
    fi
fi
LOG_LEVEL=$(docker compose exec -T ocr-service printenv LOG_LEVEL 2>/dev/null || echo "INFO")
echo "   LOG_LEVEL: $LOG_LEVEL"
echo ""
 
# 2. Check Services Status
echo "2. Checking Service Status..."
echo "----------------------------------------"
if docker compose ps ocr-service | grep -q "Up"; then
    print_status 0 "OCR Service is running"
else
    print_status 1 "OCR Service is NOT running"
fi
 
if docker compose ps fluent-bit | grep -q "Up"; then
    print_status 0 "Fluent-bit is running"
else
    print_status 1 "Fluent-bit is NOT running"
fi
 
if docker compose ps opensearch | grep -q "Up"; then
    print_status 0 "OpenSearch is running"
else
    print_status 1 "OpenSearch is NOT running"
fi
 
if docker compose ps opensearch-dashboards | grep -q "Up"; then
    print_status 0 "OpenSearch Dashboards is running"
else
    print_status 1 "OpenSearch Dashboards is NOT running"
fi
echo ""
 
# 3. Check Recent OCR Service Logs
echo "3. Checking Recent OCR Service Logs (last 5 lines)..."
echo "----------------------------------------"
RECENT_LOGS=$(docker compose logs ocr-service --tail 5 2>/dev/null || echo "")
if [ -z "$RECENT_LOGS" ]; then
    print_status 1 "No logs found from OCR service"
else
    print_status 0 "Found logs from OCR service"
    echo "$RECENT_LOGS" | tail -3
    # Check if logs are JSON format
    if echo "$RECENT_LOGS" | grep -q '"service"'; then
        print_status 0 "Logs are in JSON format"
        # Check service name in logs
        if echo "$RECENT_LOGS" | grep -q '"service".*"ocr-service"'; then
            print_status 0 "Logs contain service: 'ocr-service'"
        else
            print_status 1 "Logs do NOT contain service: 'ocr-service'"
            echo "   → Check SERVICE_NAME environment variable"
        fi
    else
        print_status 1 "Logs are NOT in JSON format"
        echo "   → Logging might not be configured correctly"
    fi
fi
echo ""
 
# 4. Check Fluent-bit Logs
echo "4. Checking Fluent-bit Logs (last 10 lines)..."
echo "----------------------------------------"
FLUENT_LOGS=$(docker compose logs fluent-bit --tail 10 2>/dev/null || echo "")
if [ -z "$FLUENT_LOGS" ]; then
    print_status 1 "No logs found from Fluent-bit"
else
    print_status 0 "Found logs from Fluent-bit"
    # Check for errors
    if echo "$FLUENT_LOGS" | grep -qi "error\|failed\|denied"; then
        print_status 1 "Fluent-bit logs contain errors:"
        echo "$FLUENT_LOGS" | grep -i "error\|failed\|denied" | head -3
    else
        print_status 0 "No obvious errors in Fluent-bit logs"
    fi
    echo "$FLUENT_LOGS" | tail -3
fi
echo ""
 
# 5. Check OpenSearch Health
echo "5. Checking OpenSearch Health..."
echo "----------------------------------------"
OPENSEARCH_HEALTH=$(curl -s http://localhost:9204/_cluster/health 2>/dev/null || echo "")
if [ -z "$OPENSEARCH_HEALTH" ]; then
    print_status 1 "Cannot connect to OpenSearch at http://localhost:9204"
    echo "   → Check if OpenSearch is running and port 9204 is accessible"
else
    print_status 0 "OpenSearch is accessible"
    STATUS=$(echo "$OPENSEARCH_HEALTH" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    echo "   Cluster status: $STATUS"
    if [ "$STATUS" = "green" ] || [ "$STATUS" = "yellow" ]; then
        print_status 0 "OpenSearch cluster is healthy"
    else
        print_status 1 "OpenSearch cluster status is: $STATUS"
    fi
fi
echo ""
 
# 6. Check OpenSearch Connection from Fluent-bit
echo "6. Testing OpenSearch Connection from Fluent-bit..."
echo "----------------------------------------"
FLUENT_OPENSEARCH_TEST=$(docker compose exec -T fluent-bit curl -s http://opensearch:9200/_cluster/health 2>/dev/null || echo "")
if [ -z "$FLUENT_OPENSEARCH_TEST" ]; then
    print_status 1 "Fluent-bit cannot connect to OpenSearch"
    echo "   → Check network connectivity and fluent-bit.conf configuration"
else
    print_status 0 "Fluent-bit can connect to OpenSearch"
    FLUENT_STATUS=$(echo "$FLUENT_OPENSEARCH_TEST" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    echo "   Connection test status: $FLUENT_STATUS"
fi
echo ""
 
# 7. Check Docker Logs Path Access
echo "7. Checking Docker Logs Path Access..."
echo "----------------------------------------"
DOCKER_LOGS_CHECK=$(docker compose exec -T fluent-bit ls -la /var/lib/docker/containers 2>/dev/null | head -3 || echo "")
if [ -z "$DOCKER_LOGS_CHECK" ]; then
    print_status 1 "Fluent-bit cannot access /var/lib/docker/containers"
    echo "   → Check volume mount in docker-compose.yml"
    echo "   → Should have: /var/lib/docker/containers:/var/lib/docker/containers:ro"
else
    print_status 0 "Fluent-bit can access Docker logs path"
    echo "   Found $(echo "$DOCKER_LOGS_CHECK" | wc -l) items in /var/lib/docker/containers"
fi
echo ""
 
# 8. Check OpenSearch Indices
echo "8. Checking OpenSearch Indices..."
echo "----------------------------------------"
INDICES=$(curl -s http://localhost:9204/_cat/indices?v 2>/dev/null | grep -E "logs|green|yellow" || echo "")
if [ -z "$INDICES" ]; then
    print_status 1 "No 'logs' indices found in OpenSearch"
    echo "   → Fluent-bit might not be sending logs yet"
else
    print_status 0 "Found indices in OpenSearch:"
    echo "$INDICES" | head -5
fi
echo ""
 
# 9. Check Recent Logs in OpenSearch
echo "9. Checking Recent Logs in OpenSearch (last 5)..."
echo "----------------------------------------"
RECENT_OPENSEARCH_LOGS=$(curl -s "http://localhost:9204/logs*/_search?size=5&sort=@timestamp:desc" 2>/dev/null || echo "")
if [ -z "$RECENT_OPENSEARCH_LOGS" ]; then
    print_status 1 "Cannot query OpenSearch for logs"
else
    # Check if we have any OCR service logs
    OCR_LOGS_COUNT=$(echo "$RECENT_OPENSEARCH_LOGS" | grep -o '"service".*"ocr-service"' | wc -l || echo "0")
    if [ "$OCR_LOGS_COUNT" -gt 0 ]; then
        print_status 0 "Found OCR service logs in OpenSearch"
        echo "   → Logs are being indexed successfully"
    else
        print_status 1 "No OCR service logs found in recent OpenSearch results"
        echo "   → Check if OCR service is logging and Fluent-bit is processing logs"
        # Show what service names we do have
        OTHER_SERVICES=$(echo "$RECENT_OPENSEARCH_LOGS" | grep -o '"service":"[^"]*"' | sort -u | head -3 || echo "")
        if [ ! -z "$OTHER_SERVICES" ]; then
            echo "   Found these service names instead:"
            echo "$OTHER_SERVICES" | sed 's/^/     /'
        fi
    fi
fi
echo ""
 
# Summary
echo "=========================================="
echo "Summary & Recommendations"
echo "=========================================="
echo ""
 
ISSUES=0
 
if [ -z "$SERVICE_NAME" ] || [ "$SERVICE_NAME" != "ocr-service" ]; then
    echo -e "${RED}✗ ISSUE:${NC} SERVICE_NAME is not set to 'ocr-service'"
    echo "   Fix: Set SERVICE_NAME=ocr-service in services/ocr-service/.env"
    echo "   Then restart: docker compose restart ocr-service"
    echo ""
    ISSUES=$((ISSUES + 1))
fi
 
if ! docker compose ps fluent-bit | grep -q "Up"; then
    echo -e "${RED}✗ ISSUE:${NC} Fluent-bit is not running"
    echo "   Fix: docker compose up -d fluent-bit"
    echo ""
    ISSUES=$((ISSUES + 1))
fi
 
if ! docker compose ps opensearch | grep -q "Up"; then
    echo -e "${RED}✗ ISSUE:${NC} OpenSearch is not running"
    echo "   Fix: docker compose up -d opensearch"
    echo ""
    ISSUES=$((ISSUES + 1))
fi
 
if [ -z "$FLUENT_OPENSEARCH_TEST" ]; then
    echo -e "${RED}✗ ISSUE:${NC} Fluent-bit cannot connect to OpenSearch"
    echo "   Fix: Check network configuration and fluent-bit.conf"
    echo ""
    ISSUES=$((ISSUES + 1))
fi
 
if [ "$ISSUES" -eq 0 ]; then
    echo -e "${GREEN}✓${NC} All basic checks passed!"
    echo ""
    echo "If logs still don't appear in OpenSearch Dashboard:"
    echo "1. Wait 2-5 minutes after making a request (Fluent-bit processing delay)"
    echo "2. Check time range in OpenSearch Dashboard (set to 'Last 15 minutes')"
    echo "3. Use this search query: service:\"ocr-service\" AND message:\"/api/v1/ocr/inference\""
    echo "4. Make a test request: curl -X POST http://localhost:8099/api/v1/ocr/inference ..."
else
    echo -e "${YELLOW}Found $ISSUES issue(s) above. Fix them and run this script again.${NC}"
fi
 
echo ""
echo "For detailed troubleshooting guide, see:"
echo "docs/TROUBLESHOOTING_OCR_LOGS_OPENSEARCH.md"
echo ""
 
 