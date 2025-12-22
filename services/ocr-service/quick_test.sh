#!/bin/bash

echo "🧪 Testing OCR Service Structured Logging"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Service Health
echo "1️⃣  Testing service health..."
if curl -s http://localhost:8099/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Service is running${NC}"
else
    echo -e "${RED}❌ Service not responding - make sure OCR service is running${NC}"
    exit 1
fi

sleep 1

# Test 2: JSON Log Format
echo ""
echo "2️⃣  Testing JSON log format..."
curl -s http://localhost:8099/health > /dev/null
sleep 2
LOG_COUNT=$(docker compose logs ocr-service --tail 10 2>/dev/null | grep -c '^{"timestamp' || echo "0")
if [ "$LOG_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ JSON logs detected (found $LOG_COUNT JSON log entries)${NC}"
else
    echo -e "${RED}❌ No JSON logs found - logs might still be in plain text format${NC}"
fi

# Test 3: Correlation ID
echo ""
echo "3️⃣  Testing correlation ID extraction..."
TEST_CORR_ID="test-corr-$(date +%s)"
curl -s -H "X-Correlation-ID: $TEST_CORR_ID" http://localhost:8099/health > /dev/null
sleep 2
CORR_FOUND=$(docker compose logs ocr-service --tail 20 2>/dev/null | grep -c "$TEST_CORR_ID" || echo "0")
if [ "$CORR_FOUND" -gt 0 ]; then
    echo -e "${GREEN}✅ Correlation ID extracted correctly (found: $TEST_CORR_ID)${NC}"
else
    echo -e "${RED}❌ Correlation ID not found in logs${NC}"
fi

# Test 4: Auto-generated Trace ID
echo ""
echo "4️⃣  Testing auto-generated trace ID..."
curl -s http://localhost:8099/health > /dev/null
sleep 2
UUID_FOUND=$(docker compose logs ocr-service --tail 10 2>/dev/null | grep -oE '"trace_id":\s*"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"' | wc -l)
if [ "$UUID_FOUND" -gt 0 ]; then
    echo -e "${GREEN}✅ Auto-generated trace ID detected${NC}"
else
    echo -e "${YELLOW}⚠️  No UUID trace ID found (might be using custom correlation ID)${NC}"
fi

# Test 5: Show Sample Log
echo ""
echo "5️⃣  Sample log entry (last log):"
echo "-----------------------------------"
SAMPLE_LOG=$(docker compose logs ocr-service --tail 5 2>/dev/null | grep -E '^{"timestamp' | tail -1)
if [ -n "$SAMPLE_LOG" ]; then
    echo "$SAMPLE_LOG" | python3 -m json.tool 2>/dev/null | head -20 || echo "$SAMPLE_LOG"
else
    echo -e "${YELLOW}⚠️  No JSON log found in last 5 lines${NC}"
    echo "Last 3 log lines:"
    docker compose logs ocr-service --tail 3 2>/dev/null
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Testing complete!${NC}"
echo ""
echo "💡 Tips:"
echo "   - View all logs: docker compose logs ocr-service"
echo "   - Follow logs: docker compose logs -f ocr-service"
echo "   - Test with correlation ID: curl -H 'X-Correlation-ID: my-id' http://localhost:8099/health"



