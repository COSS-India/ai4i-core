#!/bin/bash
#
# Test TTS Service /api/v1/tts/inference endpoint
#

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

TTS_URL="http://localhost:8088/api/v1/tts/inference"

echo "Testing TTS Service Inference Endpoint"
echo "======================================"
echo ""
echo "Endpoint: $TTS_URL"
echo ""

# Example 1: Hindi text to speech (Indo-Aryan model)
echo "Example 1: Hindi text to speech (Indo-Aryan model)"
PAYLOAD1='{
  "config": {
    "serviceId": "indic-tts-coqui-indo_aryan",
    "language": {
      "sourceLanguage": "hi"
    },
    "gender": "female",
    "samplingRate": 22050,
    "audioFormat": "wav"
  },
  "input": [
    {
      "source": "नमस्ते, आप कैसे हैं?"
    }
  ],
  "controlConfig": {
    "dataTracking": false
  }
}'

echo "Request:"
echo "$PAYLOAD1"
echo ""
echo "Response (first 500 chars):"
curl -s -X POST "$TTS_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD1" | head -c 500
echo "..."
echo ""
echo ""
echo "---"
echo ""

# Example 2: Multiple texts
echo "Example 2: Multiple texts in one request"
PAYLOAD2='{
  "config": {
    "serviceId": "indic-tts-coqui-indo_aryan",
    "language": {
      "sourceLanguage": "hi"
    },
    "gender": "female",
    "samplingRate": 22050,
    "audioFormat": "wav"
  },
  "input": [
    {
      "source": "नमस्ते"
    },
    {
      "source": "धन्यवाद"
    }
  ],
  "controlConfig": {
    "dataTracking": false
  }
}'

echo "Request:"
echo "$PAYLOAD2"
echo ""
echo "Response (first 500 chars):"
curl -s -X POST "$TTS_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD2" | head -c 500
echo "..."
echo ""
echo ""
echo "Done!"
