#!/bin/bash
#
# Test NMT Service /api/v1/nmt/inference endpoint
#

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

NMT_URL="http://localhost:8091/api/v1/nmt/inference"

echo "Testing NMT Service Translation Endpoint"
echo "=========================================="
echo ""
echo "Endpoint: $NMT_URL"
echo ""

# Example 1: English to Hindi translation
echo "Example 1: English to Hindi translation"
PAYLOAD1='{
  "config": {
    "serviceId": "indictrans-v2-all",
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    }
  },
  "input": [
    {
      "source": "Hello, how are you?"
    },
    {
      "source": "What is the weather today?"
    }
  ]
}'

echo "Request:"
echo "$PAYLOAD1"
echo ""
echo "Response:"
curl -s -X POST "$NMT_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD1"
echo ""
echo ""
echo "---"
echo ""

# Example 2: Hindi to English translation
echo "Example 2: Hindi to English translation"
PAYLOAD2='{
  "config": {
    "serviceId": "indictrans-v2-all",
    "language": {
      "sourceLanguage": "hi",
      "targetLanguage": "en"
    }
  },
  "input": [
    {
      "source": "नमस्ते, आप कैसे हैं?"
    }
  ]
}'

echo "Request:"
echo "$PAYLOAD2"
echo ""
echo "Response:"
curl -s -X POST "$NMT_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD2"
echo ""
echo ""
echo "Done!"
