#!/bin/bash
# Script to update Kong service IPs in kong-new-architecture.yml
# Run this if Docker container IPs change after service restarts

SUDO_PASSWORD="user@123"
KONG_CONFIG="services/Konga-API-manager/kong-new-architecture.yml"

echo "=== Updating Kong Service IPs ==="
echo ""

# Get current IPs from Kong container
echo "Fetching current service IPs..."
IPs=$(echo "$SUDO_PASSWORD" | sudo -S docker exec ai4v-kong-gateway sh -c "
getent hosts auth-service config-service asr-service tts-service nmt-service pipeline-service model-management-service llm-service 2>&1 | awk '{print \$1, \$2}'
" 2>/dev/null)

if [ -z "$IPs" ]; then
    echo "Error: Could not fetch IPs. Is Kong container running?"
    exit 1
fi

# Parse IPs
AUTH_IP=$(echo "$IPs" | grep "auth-service" | awk '{print $1}')
CONFIG_IP=$(echo "$IPs" | grep "config-service" | awk '{print $1}')
ASR_IP=$(echo "$IPs" | grep "asr-service" | awk '{print $1}')
TTS_IP=$(echo "$IPs" | grep "tts-service" | awk '{print $1}')
NMT_IP=$(echo "$IPs" | grep "nmt-service" | awk '{print $1}')
PIPELINE_IP=$(echo "$IPs" | grep "pipeline-service" | awk '{print $1}')
MODEL_MGMT_IP=$(echo "$IPs" | grep "model-management-service" | awk '{print $1}')
LLM_IP=$(echo "$IPs" | grep "llm-service" | awk '{print $1}')

echo "Current IPs:"
echo "  auth-service: $AUTH_IP"
echo "  config-service: $CONFIG_IP"
echo "  asr-service: $ASR_IP"
echo "  tts-service: $TTS_IP"
echo "  nmt-service: $NMT_IP"
echo "  pipeline-service: $PIPELINE_IP"
echo "  model-management-service: $MODEL_MGMT_IP"
echo "  llm-service: $LLM_IP"
echo ""

# Update kong-new-architecture.yml
if [ -f "$KONG_CONFIG" ]; then
    echo "Updating $KONG_CONFIG..."
    
    # Update each service target
    sed -i "s|target: [0-9.]*:8081|target: $AUTH_IP:8081|g" "$KONG_CONFIG"
    sed -i "s|target: [0-9.]*:8082|target: $CONFIG_IP:8082|g" "$KONG_CONFIG"
    sed -i "s|target: [0-9.]*:8087|target: $ASR_IP:8087|g" "$KONG_CONFIG"
    sed -i "s|target: [0-9.]*:8088|target: $TTS_IP:8088|g" "$KONG_CONFIG"
    sed -i "s|target: [0-9.]*:8089|target: $NMT_IP:8089|g" "$KONG_CONFIG"
    sed -i "s|target: [0-9.]*:8090.*pipeline|target: $PIPELINE_IP:8090|g" "$KONG_CONFIG"
    sed -i "s|target: [0-9.]*:8091|target: $MODEL_MGMT_IP:8091|g" "$KONG_CONFIG"
    sed -i "s|target: [0-9.]*:8090.*llm|target: $LLM_IP:8090|g" "$KONG_CONFIG"
    
    # Update auth_service_url in plugin configurations
    sed -i "s|auth_service_url: \"http://[0-9.]*:8081/api/v1/auth/validate\"|auth_service_url: \"http://$AUTH_IP:8081/api/v1/auth/validate\"|g" "$KONG_CONFIG"
    
    echo "✓ Configuration updated"
    echo ""
    echo "Restarting Kong to apply changes..."
    echo "$SUDO_PASSWORD" | sudo -S docker compose -f docker-compose.kong.yml restart kong 2>&1 | tail -3
    
    echo ""
    echo "=== Update Complete ==="
else
    echo "Error: $KONG_CONFIG not found"
    exit 1
fi

