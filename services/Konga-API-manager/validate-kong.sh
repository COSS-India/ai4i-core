#!/bin/bash
# Kong Gateway Validation Script for AIV4-Core
# This script validates all Kong capabilities

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counter for results
PASSED=0
FAILED=0
WARNINGS=0

# Helper functions
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    ((WARNINGS++))
}

info() {
    echo -e "${YELLOW}ℹ INFO${NC}: $1"
}

# Check if required tools are installed
check_dependencies() {
    info "Checking dependencies..."
    command -v curl >/dev/null 2>&1 || { fail "curl is required but not installed"; exit 1; }
    command -v jq >/dev/null 2>&1 || { fail "jq is required but not installed"; exit 1; }
    command -v docker >/dev/null 2>&1 || { fail "docker is required but not installed"; exit 1; }
    pass "All dependencies available"
}

# Check if Kong is running
check_kong_running() {
    info "Checking if Kong is running..."
    if curl -s http://localhost:8001/status > /dev/null 2>&1; then
        pass "Kong is running and accessible"
    else
        fail "Kong is not running or not accessible at http://localhost:8001"
        exit 1
    fi
}

# Load environment variables
load_env() {
    if [ -f .env ]; then
        source .env 2>/dev/null || true
        pass "Environment variables loaded from .env"
    else
        warn ".env file not found, using defaults or environment"
    fi
}

# Phase 1: Basic Connectivity
validate_basic_connectivity() {
    echo ""
    echo "=== Phase 1: Basic Connectivity ==="
    
    # Kong health
    if response=$(curl -s http://localhost:8001/status); then
        db_reachable=$(echo "$response" | jq -r '.database.reachable // false')
        if [ "$db_reachable" = "true" ]; then
            pass "Kong database is reachable"
        else
            warn "Kong database reachability status unclear"
        fi
    else
        fail "Cannot connect to Kong Admin API"
    fi
    
    # Konga access
    if curl -s http://localhost:8002 > /dev/null 2>&1; then
        pass "Kong Manager (Konga) is accessible"
    else
        warn "Kong Manager (Konga) may not be running at http://localhost:8002"
    fi
}

# Phase 2: Services and Routes
validate_services_routes() {
    echo ""
    echo "=== Phase 2: Services and Routes ==="
    
    # Count services
    service_count=$(curl -s http://localhost:8001/services | jq '.data | length')
    if [ "$service_count" -eq 10 ]; then
        pass "All 10 services are registered"
    else
        fail "Expected 10 services, found $service_count"
    fi
    
    # List services
    expected_services=("auth-service" "config-service" "metrics-service" "telemetry-service" \
                       "alerting-service" "dashboard-service" "asr-service" "tts-service" \
                       "nmt-service" "pipeline-service")
    
    services=$(curl -s http://localhost:8001/services | jq -r '.data[].name')
    for expected in "${expected_services[@]}"; do
        if echo "$services" | grep -q "^${expected}$"; then
            pass "Service $expected is registered"
        else
            fail "Service $expected is missing"
        fi
    done
    
    # Count routes
    route_count=$(curl -s http://localhost:8001/routes | jq '.data | length')
    if [ "$route_count" -eq 10 ]; then
        pass "All 10 routes are configured"
    else
        fail "Expected 10 routes, found $route_count"
    fi
}

# Phase 3: Upstreams and Targets
validate_upstreams() {
    echo ""
    echo "=== Phase 3: Upstreams and Targets ==="
    
    # Count upstreams
    upstream_count=$(curl -s http://localhost:8001/upstreams | jq '.data | length')
    if [ "$upstream_count" -eq 10 ]; then
        pass "All 10 upstreams are configured"
    else
        fail "Expected 10 upstreams, found $upstream_count"
    fi
    
    # Check targets for key services
    key_upstreams=("asr-service-upstream" "tts-service-upstream")
    for upstream in "${key_upstreams[@]}"; do
        target_count=$(curl -s "http://localhost:8001/upstreams/$upstream/targets" | jq '.data | length')
        if [ "$target_count" -ge 1 ]; then
            pass "Upstream $upstream has $target_count target(s)"
        else
            fail "Upstream $upstream has no targets"
        fi
    done
}

# Phase 4: Authentication
validate_authentication() {
    echo ""
    echo "=== Phase 4: Authentication ==="
    
    # Count consumers
    consumer_count=$(curl -s http://localhost:8001/consumers | jq '.data | length')
    if [ "$consumer_count" -eq 6 ]; then
        pass "All 6 consumers are registered"
    else
        fail "Expected 6 consumers, found $consumer_count"
    fi
    
    # Check consumers
    expected_consumers=("ai4voice-client" "asr-client" "tts-client" "nmt-client" "pipeline-client" "developer-client")
    consumers=$(curl -s http://localhost:8001/consumers | jq -r '.data[].username')
    
    for expected in "${expected_consumers[@]}"; do
        if echo "$consumers" | grep -q "^${expected}$"; then
            pass "Consumer $expected is registered"
            
            # Check API keys
            key_count=$(curl -s "http://localhost:8001/consumers/$expected/key-auth" | jq '.data | length')
            if [ "$key_count" -ge 1 ]; then
                pass "Consumer $expected has API key(s)"
            else
                fail "Consumer $expected has no API keys"
            fi
        else
            fail "Consumer $expected is missing"
        fi
    done
    
    # Test authentication with API key
    if [ -n "$ASR_API_KEY" ]; then
        response_code=$(curl -s -w "%{http_code}" -o /dev/null \
            "http://localhost:8000/api/v1/asr/health" \
            -H "X-API-Key: $ASR_API_KEY")
        
        if [ "$response_code" != "401" ] && [ "$response_code" != "000" ]; then
            pass "Authentication works with ASR_API_KEY (response: $response_code)"
        else
            fail "Authentication failed with ASR_API_KEY (response: $response_code)"
        fi
        
        # Test without API key
        response_code=$(curl -s -w "%{http_code}" -o /dev/null \
            "http://localhost:8000/api/v1/asr/health")
        
        if [ "$response_code" = "401" ]; then
            pass "Protected endpoints reject requests without API key"
        else
            fail "Protected endpoints should return 401 without API key (got: $response_code)"
        fi
    else
        warn "ASR_API_KEY not set, skipping authentication test"
    fi
}

# Phase 5: Rate Limiting
validate_rate_limiting() {
    echo ""
    echo "=== Phase 5: Rate Limiting ==="
    
    # Check rate-limiting plugin on services
    services_with_rate_limit=0
    for service in auth-service asr-service tts-service; do
        plugin_count=$(curl -s "http://localhost:8001/services/$service/plugins" | \
            jq '[.data[] | select(.name=="rate-limiting")] | length')
        if [ "$plugin_count" -ge 1 ]; then
            pass "Service $service has rate-limiting plugin"
            ((services_with_rate_limit++))
        else
            fail "Service $service missing rate-limiting plugin"
        fi
    done
    
    # Check Redis configuration
    redis_config=$(curl -s "http://localhost:8001/services/asr-service/plugins" | \
        jq '.data[] | select(.name=="rate-limiting") | .config.redis')
    
    if [ -n "$redis_config" ] && [ "$redis_config" != "null" ]; then
        redis_host=$(echo "$redis_config" | jq -r '.host // empty')
        if [ "$redis_host" = "redis" ]; then
            pass "Rate limiting uses Redis backend"
        else
            warn "Rate limiting Redis host is '$redis_host', expected 'redis'"
        fi
    else
        warn "Could not verify Redis configuration for rate limiting"
    fi
}

# Phase 6: Plugins
validate_plugins() {
    echo ""
    echo "=== Phase 6: Plugins ==="
    
    # Global plugins
    global_plugins=$(curl -s http://localhost:8001/plugins | jq -r '.data[] | select(.service == null and .route == null) | .name')
    
    if echo "$global_plugins" | grep -q "prometheus"; then
        pass "Prometheus plugin is enabled globally"
    else
        fail "Prometheus plugin is not enabled globally"
    fi
    
    if echo "$global_plugins" | grep -q "correlation-id"; then
        pass "Correlation-ID plugin is enabled globally"
    else
        fail "Correlation-ID plugin is not enabled globally"
    fi
    
    if echo "$global_plugins" | grep -q "request-id"; then
        pass "Request-ID plugin is enabled globally"
    else
        fail "Request-ID plugin is not enabled globally"
    fi
    
    # Service plugins
    asr_plugins=$(curl -s "http://localhost:8001/services/asr-service/plugins" | jq -r '.data[].name')
    
    if echo "$asr_plugins" | grep -q "key-auth"; then
        pass "ASR service has key-auth plugin"
    else
        fail "ASR service missing key-auth plugin"
    fi
    
    if echo "$asr_plugins" | grep -q "cors"; then
        pass "ASR service has CORS plugin"
    else
        fail "ASR service missing CORS plugin"
    fi
    
    if echo "$asr_plugins" | grep -q "request-transformer"; then
        pass "ASR service has request-transformer plugin"
    else
        fail "ASR service missing request-transformer plugin"
    fi
}

# Phase 7: Metrics
validate_metrics() {
    echo ""
    echo "=== Phase 7: Metrics ==="
    
    # Check Prometheus metrics endpoint
    if metrics=$(curl -s http://localhost:8001/metrics); then
        if echo "$metrics" | grep -q "kong_http_requests_total"; then
            pass "Prometheus metrics endpoint accessible"
            
            # Count metrics
            metric_count=$(echo "$metrics" | grep -c "^kong_" || true)
            if [ "$metric_count" -gt 0 ]; then
                pass "Found $metric_count Kong metrics"
            else
                warn "No Kong metrics found in Prometheus endpoint"
            fi
        else
            fail "Prometheus metrics endpoint missing key metrics"
        fi
    else
        fail "Cannot access Prometheus metrics endpoint"
    fi
}

# Phase 8: End-to-End Testing
validate_e2e() {
    echo ""
    echo "=== Phase 8: End-to-End Testing ==="
    
    # Test public endpoint (auth-service)
    response_code=$(curl -s -w "%{http_code}" -o /dev/null "http://localhost:8000/api/v1/auth/health")
    if [ "$response_code" != "401" ]; then
        pass "Public endpoint (auth-service) accessible without authentication"
    else
        fail "Public endpoint (auth-service) should not require authentication"
    fi
    
    # Test protected endpoints
    if [ -n "$ASR_API_KEY" ]; then
        response_code=$(curl -s -w "%{http_code}" -o /dev/null \
            "http://localhost:8000/api/v1/asr/health" \
            -H "X-API-Key: $ASR_API_KEY")
        if [ "$response_code" != "401" ] && [ "$response_code" != "000" ]; then
            pass "Protected endpoint (ASR) accessible with valid API key"
        else
            warn "ASR endpoint returned $response_code (service may not be running)"
        fi
    fi
    
    # Test invalid route
    response_code=$(curl -s -w "%{http_code}" -o /dev/null "http://localhost:8000/api/v1/nonexistent")
    if [ "$response_code" = "404" ]; then
        pass "Invalid routes return 404"
    else
        warn "Invalid route returned $response_code, expected 404"
    fi
}

# Main execution
main() {
    echo "=========================================="
    echo "  Kong Gateway Validation Script"
    echo "  AIV4-Core Microservices"
    echo "=========================================="
    echo ""
    
    check_dependencies
    check_kong_running
    load_env
    
    validate_basic_connectivity
    validate_services_routes
    validate_upstreams
    validate_authentication
    validate_rate_limiting
    validate_plugins
    validate_metrics
    validate_e2e
    
    # Summary
    echo ""
    echo "=========================================="
    echo "  Validation Summary"
    echo "=========================================="
    echo -e "${GREEN}Passed:${NC} $PASSED"
    echo -e "${RED}Failed:${NC} $FAILED"
    echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
    echo ""
    
    total=$((PASSED + FAILED + WARNINGS))
    if [ "$FAILED" -eq 0 ]; then
        echo -e "${GREEN}✓ All critical validations passed!${NC}"
        exit 0
    else
        echo -e "${RED}✗ Some validations failed${NC}"
        exit 1
    fi
}

# Run main function
main "$@"

