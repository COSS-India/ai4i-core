#!/bin/sh
# Script to resolve service hostnames to IPs and substitute them in kong-new-architecture.yml
# This makes the configuration portable across different machines

KONG_CONFIG="/kong/kong-new-architecture.yml"
SUBSTITUTED_CONFIG="/tmp/kong-substituted.yml"

echo "=== Resolving service IPs dynamically ==="

# Function to resolve service IP
resolve_service_ip() {
    local service_name=$1
    local ip=$(getent hosts "$service_name" 2>/dev/null | awk '{print $1}' | head -1)
    if [ -z "$ip" ]; then
        echo "Warning: Could not resolve $service_name, keeping original value" >&2
        echo ""
    else
        echo "$ip"
    fi
}

# Resolve all service IPs
AUTH_IP=$(resolve_service_ip "auth-service")
CONFIG_IP=$(resolve_service_ip "config-service")
ASR_IP=$(resolve_service_ip "asr-service")
TTS_IP=$(resolve_service_ip "tts-service")
NMT_IP=$(resolve_service_ip "nmt-service")
PIPELINE_IP=$(resolve_service_ip "pipeline-service")
MODEL_MGMT_IP=$(resolve_service_ip "model-management-service")
LLM_IP=$(resolve_service_ip "llm-service")

echo "Resolved IPs:"
[ -n "$AUTH_IP" ] && echo "  auth-service: $AUTH_IP"
[ -n "$CONFIG_IP" ] && echo "  config-service: $CONFIG_IP"
[ -n "$ASR_IP" ] && echo "  asr-service: $ASR_IP"
[ -n "$TTS_IP" ] && echo "  tts-service: $TTS_IP"
[ -n "$NMT_IP" ] && echo "  nmt-service: $NMT_IP"
[ -n "$PIPELINE_IP" ] && echo "  pipeline-service: $PIPELINE_IP"
[ -n "$MODEL_MGMT_IP" ] && echo "  model-management-service: $MODEL_MGMT_IP"
[ -n "$LLM_IP" ] && echo "  llm-service: $LLM_IP"
echo ""

# Copy original config to substituted location (substitute-env.sh will use this)
# We'll modify it in place, then substitute-env.sh will process it further
cp "$KONG_CONFIG" "$SUBSTITUTED_CONFIG"

# Substitute IPs in targets section (only if IPs were resolved)
# If IP resolution fails, keep hostnames (they might work if DNS is fixed)
if [ -n "$AUTH_IP" ]; then
    sed -i "s|target: auth-service:8081|target: $AUTH_IP:8081|g" "$SUBSTITUTED_CONFIG"
    sed -i "s|auth_service_url: \"http://auth-service:8081|auth_service_url: \"http://$AUTH_IP:8081|g" "$SUBSTITUTED_CONFIG"
    echo "  ✓ Resolved auth-service to $AUTH_IP"
else
    echo "  ⚠ Keeping auth-service hostname (DNS resolution failed)"
fi

if [ -n "$CONFIG_IP" ]; then
    sed -i "s|target: config-service:8082|target: $CONFIG_IP:8082|g" "$SUBSTITUTED_CONFIG"
    echo "  ✓ Resolved config-service to $CONFIG_IP"
else
    echo "  ⚠ Keeping config-service hostname (DNS resolution failed)"
fi

if [ -n "$ASR_IP" ]; then
    sed -i "s|target: asr-service:8087|target: $ASR_IP:8087|g" "$SUBSTITUTED_CONFIG"
    echo "  ✓ Resolved asr-service to $ASR_IP"
fi

if [ -n "$TTS_IP" ]; then
    sed -i "s|target: tts-service:8088|target: $TTS_IP:8088|g" "$SUBSTITUTED_CONFIG"
    echo "  ✓ Resolved tts-service to $TTS_IP"
fi

if [ -n "$NMT_IP" ]; then
    sed -i "s|target: nmt-service:8089|target: $NMT_IP:8089|g" "$SUBSTITUTED_CONFIG"
    echo "  ✓ Resolved nmt-service to $NMT_IP"
fi

if [ -n "$PIPELINE_IP" ]; then
    sed -i "s|target: pipeline-service:8090|target: $PIPELINE_IP:8090|g" "$SUBSTITUTED_CONFIG"
    echo "  ✓ Resolved pipeline-service to $PIPELINE_IP"
fi

if [ -n "$MODEL_MGMT_IP" ]; then
    sed -i "s|target: model-management-service:8091|target: $MODEL_MGMT_IP:8091|g" "$SUBSTITUTED_CONFIG"
    echo "  ✓ Resolved model-management-service to $MODEL_MGMT_IP"
fi

if [ -n "$LLM_IP" ]; then
    sed -i "s|target: llm-service:8090|target: $LLM_IP:8090|g" "$SUBSTITUTED_CONFIG"
    echo "  ✓ Resolved llm-service to $LLM_IP"
fi

echo "✓ Configuration prepared with resolved IPs"
echo ""

