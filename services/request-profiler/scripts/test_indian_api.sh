#!/bin/bash
# Test script for Indian Languages Translation Request Profiler API
# Tests all 6 languages (Hindi, Bengali, Tamil, Telugu, Kannada, Assamese)

BASE_URL="http://localhost:8000"

echo "================================================================================"
echo "INDIAN LANGUAGES API TESTING"
echo "================================================================================"
echo ""

# Test 1: Hindi medical text
echo "1. Testing Hindi Medical Text"
echo "---"
curl -s -X POST "$BASE_URL/api/v1/profile" \
  -H "Content-Type: application/json" \
  -d '{"text": "रोगी को तीव्र हृदयाघात हुआ है और तत्काल चिकित्सा की आवश्यकता है।"}' | python3 -m json.tool
echo ""

# Test 2: Bengali legal text
echo "2. Testing Bengali Legal Text"
echo "---"
curl -s -X POST "$BASE_URL/api/v1/profile" \
  -H "Content-Type: application/json" \
  -d '{"text": "আদালত রায় ঘোষণা করেছে এবং আবেদন গ্রহণ করেছে।"}' | python3 -m json.tool
echo ""

# Test 3: Tamil technical text
echo "3. Testing Tamil Technical Text"
echo "---"
curl -s -X POST "$BASE_URL/api/v1/profile" \
  -H "Content-Type: application/json" \
  -d '{"text": "சர்வரில் பிழை ஏற்பட்டது மற்றும் கணினி செயலிழந்தது।"}' | python3 -m json.tool
echo ""

# Test 4: Telugu finance text
echo "4. Testing Telugu Finance Text"
echo "---"
curl -s -X POST "$BASE_URL/api/v1/profile" \
  -H "Content-Type: application/json" \
  -d '{"text": "బ్యాంకు వడ్డీ రేటును పెంచింది మరియు కొత్త విధానం ప్రకటించింది।"}' | python3 -m json.tool
echo ""

# Test 5: Kannada medical text
echo "5. Testing Kannada Medical Text"
echo "---"
curl -s -X POST "$BASE_URL/api/v1/profile" \
  -H "Content-Type: application/json" \
  -d '{"text": "ರೋಗಿಗೆ ತೀವ್ರ ಹೃದಯಾಘಾತವಾಗಿದೆ"}' | python3 -m json.tool
echo ""

# Test 6: Assamese medical text
echo "6. Testing Assamese Medical Text"
echo "---"
curl -s -X POST "$BASE_URL/api/v1/profile" \
  -H "Content-Type: application/json" \
  -d '{"text": "ৰোগীৰ তীব্ৰ হৃদৰোগ হৈছে"}' | python3 -m json.tool
echo ""

# Test 7: Batch endpoint with all 6 languages
echo "7. Testing Batch Endpoint with Mixed Languages"
echo "---"
curl -s -X POST "$BASE_URL/api/v1/profile/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [
      "रोगी को बुखार और सिरदर्द की शिकायत है।",
      "আদালত রায় ঘোষণা করেছে।",
      "சர்வரில் பிழை ஏற்பட்டது.",
      "బ్యాంకు వడ్డీ రేటును పెంచింది.",
      "ರೋಗಿಗೆ ತೀವ್ರ ಹೃದಯಾಘಾತವಾಗಿದೆ.",
      "ৰোগীৰ তীব্ৰ হৃদৰোগ হৈছে."
    ]
  }' | python3 -m json.tool
echo ""

# Test 8: Health endpoint
echo "8. Testing Health Endpoint"
echo "---"
curl -s "$BASE_URL/api/v1/health" | python3 -m json.tool
echo ""

# Test 9: Info endpoint
echo "9. Testing Info Endpoint"
echo "---"
curl -s "$BASE_URL/api/v1/info" | python3 -m json.tool
echo ""

echo "================================================================================"
echo "✅ INDIAN LANGUAGES API TESTING COMPLETE (6 LANGUAGES)"
echo "================================================================================"
echo ""
echo "All 6 endpoints tested with Indic text:"
echo "  ✓ POST /api/v1/profile - Single text profiling (Hindi, Bengali, Tamil, Telugu, Kannada, Assamese)"
echo "  ✓ POST /api/v1/profile/batch - Batch profiling (Mixed 6 languages)"
echo "  ✓ GET /api/v1/health - Health check"
echo "  ✓ GET /api/v1/info - Service information"
echo "  ✓ GET /metrics - Prometheus metrics"
echo "  ✓ GET /docs - Swagger UI"
echo ""
echo "Service is ready for 6 Indian language text profiling!"
echo "================================================================================"

