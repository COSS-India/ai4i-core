#!/bin/bash
# Unified script to manage NMT Service configurations in Config Service
# Usage: 
#   ./manage-configs.sh setup [environment] [config-service-url]
#   ./manage-configs.sh clear [environment] [config-service-url]
#   ./manage-configs.sh reset [environment] [config-service-url]  # clear then setup
#
# Examples:
#   ./manage-configs.sh setup development http://localhost:8082
#   ./manage-configs.sh clear development http://localhost:8082
#   ./manage-configs.sh reset development http://localhost:8082

ACTION=${1:-setup}
ENVIRONMENT=${2:-development}
CONFIG_SERVICE_URL=${3:-http://localhost:8082}
SERVICE_NAME="nmt-service"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to create a configuration
create_config() {
    local key=$1
    local value=$2
    local encrypted=${3:-false}
    
    echo -n "Creating $key... "
    
    response=$(curl -s --connect-timeout 5 --max-time 10 -w "\n%{http_code}" -X POST "$CONFIG_SERVICE_URL/api/v1/config/" \
        -H "Content-Type: application/json" \
        -d "{
            \"key\": \"$key\",
            \"value\": \"$value\",
            \"environment\": \"$ENVIRONMENT\",
            \"service_name\": \"$SERVICE_NAME\",
            \"is_encrypted\": $encrypted
        }")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 201 ] || [ "$http_code" -eq 200 ]; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗ (HTTP $http_code)${NC}"
        if [ -n "$body" ]; then
            echo "  Response: $body"
        fi
        return 1
    fi
}

# Function to delete a configuration
delete_config() {
    local key=$1
    
    echo -n "Deleting $key... "
    
    response=$(curl -s --connect-timeout 5 --max-time 10 -w "\n%{http_code}" -X DELETE \
        "$CONFIG_SERVICE_URL/api/v1/config/$key?environment=$ENVIRONMENT&service_name=$SERVICE_NAME")
    
    http_code=$(echo "$response" | tail -n1)
    
    if [ "$http_code" -eq 204 ] || [ "$http_code" -eq 200 ]; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗ (HTTP $http_code)${NC}"
        return 1
    fi
}

# Function to clear all configurations
clear_configs() {
    echo -e "${BLUE}Clearing all configurations for $SERVICE_NAME in $ENVIRONMENT environment${NC}"
    echo "Config Service URL: $CONFIG_SERVICE_URL"
    echo ""
    
    # Get all configurations
    echo "Fetching all configurations..."
    response=$(curl -s --connect-timeout 5 --max-time 10 \
        "$CONFIG_SERVICE_URL/api/v1/config/?environment=$ENVIRONMENT&service_name=$SERVICE_NAME&limit=100")
    
    # Extract keys from JSON response
    keys=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data.get('items', [])
    keys = [item.get('key') for item in items if item.get('key')]
    print('\n'.join(keys))
except Exception:
    print('', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)
    
    if [ -z "$keys" ]; then
        echo -e "${YELLOW}No configurations found to delete.${NC}"
        return 0
    fi
    
    # Count keys
    key_count=$(echo "$keys" | wc -l)
    echo -e "${YELLOW}Found $key_count configuration(s) to delete${NC}"
    echo ""
    
    # Delete all configurations
    deleted=0
    failed=0
    
    while IFS= read -r key; do
        if [ -n "$key" ]; then
            if delete_config "$key"; then
                ((deleted++))
            else
                ((failed++))
            fi
        fi
    done <<< "$keys"
    
    echo ""
    echo -e "${GREEN}Deleted: $deleted${NC}"
    if [ $failed -gt 0 ]; then
        echo -e "${RED}Failed: $failed${NC}"
    fi
    echo ""
    echo -e "${GREEN}Configuration cleanup complete!${NC}"
}

# Function to setup all configurations
setup_configs() {
    echo -e "${BLUE}Setting up configurations for $SERVICE_NAME in $ENVIRONMENT environment${NC}"
    echo "Config Service URL: $CONFIG_SERVICE_URL"
    echo ""
    
    created=0
    failed=0
    
    # Redis Configuration
    echo "=== Redis Configuration ==="
    if create_config "REDIS_HOST" "redis" false; then ((created++)); else ((failed++)); fi
    if create_config "REDIS_PORT" "6379" false; then ((created++)); else ((failed++)); fi
    if create_config "REDIS_PASSWORD" "redis_secure_password_2024" true; then ((created++)); else ((failed++)); fi
    echo ""
    
    # PostgreSQL Configuration
    echo "=== PostgreSQL Configuration ==="
    if create_config "DATABASE_URL" "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db" true; then ((created++)); else ((failed++)); fi
    echo ""
    
    # Triton Inference Server Configuration
    echo "=== Triton Inference Server Configuration ==="
    if create_config "TRITON_ENDPOINT" "13.200.133.97:8000" false; then ((created++)); else ((failed++)); fi
    if create_config "TRITON_API_KEY" "1b69e9a1a24466c85e4bbca3c5295f50" true; then ((created++)); else ((failed++)); fi
    echo ""
    
    # Rate Limiting Configuration
    echo "=== Rate Limiting Configuration ==="
    if create_config "RATE_LIMIT_PER_MINUTE" "60" false; then ((created++)); else ((failed++)); fi
    if create_config "RATE_LIMIT_PER_HOUR" "1000" false; then ((created++)); else ((failed++)); fi
    echo ""
    
    # NMT Service Configuration
    echo "=== NMT Service Configuration ==="
    if create_config "MAX_BATCH_SIZE" "90" false; then ((created++)); else ((failed++)); fi
    if create_config "MAX_TEXT_LENGTH" "10000" false; then ((created++)); else ((failed++)); fi
    if create_config "DEFAULT_SOURCE_LANGUAGE" "en" false; then ((created++)); else ((failed++)); fi
    if create_config "DEFAULT_TARGET_LANGUAGE" "hi" false; then ((created++)); else ((failed++)); fi
    echo ""
    
    echo -e "${GREEN}Configuration setup complete!${NC}"
    echo ""
    echo -e "${GREEN}Created: $created${NC}"
    if [ $failed -gt 0 ]; then
        echo -e "${RED}Failed: $failed${NC}"
    fi
    echo ""
    echo "To verify configurations, run:"
    echo "  curl \"$CONFIG_SERVICE_URL/api/v1/config/?environment=$ENVIRONMENT&service_name=$SERVICE_NAME\""
}

# Main logic
case "$ACTION" in
    setup)
        setup_configs
        ;;
    clear)
        clear_configs
        ;;
    reset)
        clear_configs
        echo ""
        echo -e "${BLUE}Now setting up configurations...${NC}"
        echo ""
        setup_configs
        ;;
    *)
        echo -e "${RED}Error: Unknown action '$ACTION'${NC}"
        echo ""
        echo "Usage:"
        echo "  ./manage-configs.sh setup [environment] [config-service-url]"
        echo "  ./manage-configs.sh clear [environment] [config-service-url]"
        echo "  ./manage-configs.sh reset [environment] [config-service-url]"
        echo ""
        echo "Examples:"
        echo "  ./manage-configs.sh setup development http://localhost:8082"
        echo "  ./manage-configs.sh clear development http://localhost:8082"
        echo "  ./manage-configs.sh reset development http://localhost:8082"
        exit 1
        ;;
esac

