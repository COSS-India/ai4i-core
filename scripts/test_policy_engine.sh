#!/bin/bash
#
# Test Policy Engine /v1/policy/evaluate endpoint
#

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

POLICY_URL="http://localhost:8100/v1/policy/evaluate"

echo "Testing Policy Engine Evaluate Endpoint"
echo "========================================"
echo ""
echo "Endpoint: $POLICY_URL"
echo ""

# Example 1: Free user (no tenant_id)
echo "Example 1: Free user (default policy)"
PAYLOAD1='{"user_id": "user123", "tenant_id": null}'

echo "Request:"
echo "$PAYLOAD1"
echo ""
echo "Response:"
curl -s -X POST "$POLICY_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD1"
echo ""
echo ""
echo "---"
echo ""

# Example 2: Tenant user with custom policies
echo "Example 2: Tenant user with custom policies"
PAYLOAD2='{"user_id": "user456", "tenant_id": "tenant-abc", "latency_policy": "low", "cost_policy": "tier_2", "accuracy_policy": "sensitive"}'

echo "Request:"
echo "$PAYLOAD2"
echo ""
echo "Response:"
curl -s -X POST "$POLICY_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD2"
echo ""
echo ""
echo "---"
echo ""

# Example 3: High accuracy with low cost (conflict scenario)
echo "Example 3: High accuracy with low cost (conflict scenario)"
PAYLOAD3='{"user_id": "user789", "tenant_id": "tenant-xyz", "latency_policy": "medium", "cost_policy": "tier_1", "accuracy_policy": "sensitive"}'

echo "Request:"
echo "$PAYLOAD3"
echo ""
echo "Response:"
curl -s -X POST "$POLICY_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD3"
echo ""
echo ""
echo "Done!"
