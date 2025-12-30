#!/bin/sh
# Kong entrypoint script to substitute environment variables in kong.yml

set -e

# Path to kong.yml
KONG_CONFIG="/kong/kong.yml"

# Check if kong.yml exists
if [ ! -f "$KONG_CONFIG" ]; then
    echo "Error: $KONG_CONFIG not found"
    exit 1
fi

# Create a temporary file for substituted config
TMP_CONFIG="/tmp/kong-substituted.yml"

# Substitute environment variables using envsubst
# Note: envsubst only substitutes variables that are exported
export REDIS_PASSWORD AI4VOICE_API_KEY ASR_API_KEY TTS_API_KEY NMT_API_KEY PIPELINE_API_KEY DEVELOPER_API_KEY

# Use envsubst to substitute variables
envsubst < "$KONG_CONFIG" > "$TMP_CONFIG"

# Copy substituted config back to original location
cp "$TMP_CONFIG" "/kong/kong.yml"

echo "Environment variables substituted in kong.yml"

# Execute the original Kong entrypoint
exec /docker-entrypoint.sh kong docker-start

