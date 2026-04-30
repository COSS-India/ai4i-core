#!/bin/bash

# Test script for Feature Flags API
BASE_URL="http://localhost:8082/api/v1/feature-flags"
ENVIRONMENT="development"

echo "=========================================="
echo "Testing Feature Flags API Endpoints"
echo "=========================================="
echo ""

# Test 1: List feature flags (GET /)
echo "1. Testing GET /api/v1/feature-flags/ (List flags)"
echo "----------------------------------------"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "${BASE_URL}/?limit=10&offset=0")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

# Test 2: Create a test feature flag (POST /)
echo "2. Testing POST /api/v1/feature-flags/ (Create flag)"
echo "----------------------------------------"
create_payload='{
  "name": "test-flag-api",
  "description": "Test flag created via API",
  "is_enabled": true,
  "environment": "'"$ENVIRONMENT"'",
  "rollout_percentage": "50",
  "target_users": ["user1", "user2"]
}'
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST -H "Content-Type: application/json" -d "$create_payload" "${BASE_URL}/")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

# Test 3: Get feature flag by name (GET /{name})
echo "3. Testing GET /api/v1/feature-flags/{name} (Get flag)"
echo "----------------------------------------"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "${BASE_URL}/test-flag-api?environment=${ENVIRONMENT}")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

# Test 4: Evaluate feature flag (POST /evaluate)
echo "4. Testing POST /api/v1/feature-flags/evaluate (Evaluate flag)"
echo "----------------------------------------"
evaluate_payload='{
  "flag_name": "test-flag-api",
  "environment": "'"$ENVIRONMENT"'",
  "user_id": "test-user-123",
  "context": {"region": "us-east"},
  "default_value": false
}'
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST -H "Content-Type: application/json" -d "$evaluate_payload" "${BASE_URL}/evaluate")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

# Test 5: Evaluate boolean flag (POST /evaluate/boolean)
echo "5. Testing POST /api/v1/feature-flags/evaluate/boolean (Evaluate boolean)"
echo "----------------------------------------"
boolean_payload='{
  "flag_name": "test-flag-api",
  "environment": "'"$ENVIRONMENT"'",
  "user_id": "test-user-123",
  "context": {"region": "us-east"},
  "default_value": false
}'
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST -H "Content-Type: application/json" -d "$boolean_payload" "${BASE_URL}/evaluate/boolean")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

# Test 6: Bulk evaluate (POST /evaluate/bulk)
echo "6. Testing POST /api/v1/feature-flags/evaluate/bulk (Bulk evaluate)"
echo "----------------------------------------"
bulk_payload='{
  "flag_names": ["test-flag-api"],
  "environment": "'"$ENVIRONMENT"'",
  "user_id": "test-user-123",
  "context": {"region": "us-east"}
}'
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST -H "Content-Type: application/json" -d "$bulk_payload" "${BASE_URL}/evaluate/bulk")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

# Test 7: Get evaluation history (GET /{name}/history)
echo "7. Testing GET /api/v1/feature-flags/{name}/history (Get history)"
echo "----------------------------------------"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "${BASE_URL}/test-flag-api/history?environment=${ENVIRONMENT}&limit=10")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

# Test 8: Update feature flag (PUT /{name})
echo "8. Testing PUT /api/v1/feature-flags/{name} (Update flag)"
echo "----------------------------------------"
update_payload='{
  "is_enabled": false,
  "description": "Updated description"
}'
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X PUT -H "Content-Type: application/json" -d "$update_payload" "${BASE_URL}/test-flag-api?environment=${ENVIRONMENT}")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

# Test 9: Delete feature flag (DELETE /{name})
echo "9. Testing DELETE /api/v1/feature-flags/{name} (Delete flag)"
echo "----------------------------------------"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X DELETE "${BASE_URL}/test-flag-api?environment=${ENVIRONMENT}")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

# Test 10: Sync from Unleash (POST /sync) - This might fail due to auth, but let's test
echo "10. Testing POST /api/v1/feature-flags/sync (Sync from Unleash)"
echo "----------------------------------------"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "${BASE_URL}/sync?environment=${ENVIRONMENT}")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')
echo "Status: $http_code"
echo "Response: $body" | jq '.' 2>/dev/null || echo "$body"
echo ""

echo "=========================================="
echo "Testing Complete"
echo "=========================================="

