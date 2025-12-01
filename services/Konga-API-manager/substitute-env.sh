#!/bin/sh
# Substitute environment variables in kong.yml using sed

set -e

INPUT_FILE="/kong/kong.yml"
OUTPUT_FILE="/tmp/kong-substituted.yml"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: $INPUT_FILE not found" >&2
    exit 1
fi

# Copy original file
cp "$INPUT_FILE" "$OUTPUT_FILE"

# Substitute each environment variable using sed
if [ -n "$REDIS_PASSWORD" ]; then
    sed -i "s|\${REDIS_PASSWORD}|$REDIS_PASSWORD|g" "$OUTPUT_FILE"
fi

if [ -n "$AI4VOICE_API_KEY" ]; then
    sed -i "s|\${AI4VOICE_API_KEY}|$AI4VOICE_API_KEY|g" "$OUTPUT_FILE"
fi

if [ -n "$ASR_API_KEY" ]; then
    sed -i "s|\${ASR_API_KEY}|$ASR_API_KEY|g" "$OUTPUT_FILE"
fi

if [ -n "$TTS_API_KEY" ]; then
    sed -i "s|\${TTS_API_KEY}|$TTS_API_KEY|g" "$OUTPUT_FILE"
fi

if [ -n "$NMT_API_KEY" ]; then
    sed -i "s|\${NMT_API_KEY}|$NMT_API_KEY|g" "$OUTPUT_FILE"
fi

if [ -n "$PIPELINE_API_KEY" ]; then
    sed -i "s|\${PIPELINE_API_KEY}|$PIPELINE_API_KEY|g" "$OUTPUT_FILE"
fi

if [ -n "$DEVELOPER_API_KEY" ]; then
    sed -i "s|\${DEVELOPER_API_KEY}|$DEVELOPER_API_KEY|g" "$OUTPUT_FILE"
fi

echo "Environment variables substituted successfully"
echo "Substituted config written to $OUTPUT_FILE"

