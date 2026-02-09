# A/B Testing API - cURL Examples

This document provides comprehensive cURL commands to test all A/B testing functionalities.

## Prerequisites

- **Base URL**: `http://localhost:8000` (API Gateway) or `http://localhost:8091` (Model Management Service directly)
- **Auth Token**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZW1haWwiOiJnZW9AZ21haWwuY29tIiwidXNlcm5hbWUiOiJnZW8iLCJleHAiOjE3OTkzODQ3NTgsInR5cGUiOiJhY2Nlc3MiLCJyb2xlcyI6WyJBRE1JTiJdfQ.UMwkHVhGPkkVJq5xZ0Xw4QOPrMimewNLqq_n06As05Q`
- **Note**: You need at least 2 published services with different service IDs to create experiments

## Environment Variables

```bash
export BASE_URL="http://localhost:8000"  # API Gateway
# OR
export BASE_URL="http://localhost:8091"  # Model Management Service directly

export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZW1haWwiOiJnZW9AZ21haWwuY29tIiwidXNlcm5hbWUiOiJnZW8iLCJleHAiOjE3OTkzODQ3NTgsInR5cGUiOiJhY2Nlc3MiLCJyb2xlcyI6WyJBRE1JTiJdfQ.UMwkHVhGPkkVJq5xZ0Xw4QOPrMimewNLqq_n06As05Q"
```

---

## 1. Create an Experiment

Creates a new A/B testing experiment with multiple variants.

```bash
curl -X POST "${BASE_URL}/api/v1/model-management/experiments" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "name": "ASR Model Comparison v1 vs v2",
    "description": "Compare performance of ASR model v1.0 vs v2.0",
    "task_type": ["asr"],
    "languages": ["hi", "en"],
    "start_date": "2024-01-01T00:00:00Z",
    "end_date": "2024-12-31T23:59:59Z",
    "variants": [
      {
        "variant_name": "control",
        "service_id": "YOUR_SERVICE_ID_1",
        "traffic_percentage": 50,
        "description": "Current production model (v1.0)"
      },
      {
        "variant_name": "variant-a",
        "service_id": "YOUR_SERVICE_ID_2",
        "traffic_percentage": 50,
        "description": "New model version (v2.0)"
      }
    ]
  }'
```

**Response**: Returns the created experiment with ID.

**Note**: Replace `YOUR_SERVICE_ID_1` and `YOUR_SERVICE_ID_2` with actual published service IDs.

---

## 2. List All Experiments

Lists all experiments with optional filters.

```bash
# List all experiments
curl -X GET "${BASE_URL}/api/v1/model-management/experiments" \
  -H "Authorization: Bearer ${TOKEN}"

# Filter by status
curl -X GET "${BASE_URL}/api/v1/model-management/experiments?status=RUNNING" \
  -H "Authorization: Bearer ${TOKEN}"

# Filter by task type
curl -X GET "${BASE_URL}/api/v1/model-management/experiments?task_type=asr" \
  -H "Authorization: Bearer ${TOKEN}"

# Filter by creator
curl -X GET "${BASE_URL}/api/v1/model-management/experiments?created_by=2" \
  -H "Authorization: Bearer ${TOKEN}"

# Combined filters
curl -X GET "${BASE_URL}/api/v1/model-management/experiments?status=RUNNING&task_type=asr" \
  -H "Authorization: Bearer ${TOKEN}"
```

---

## 3. Get Experiment Details

Retrieves detailed information about a specific experiment.

```bash
# Replace EXPERIMENT_ID with actual experiment ID from create response
export EXPERIMENT_ID="your-experiment-uuid"

curl -X GET "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
```

---

## 4. Update Experiment

Updates experiment configuration (name, description, filters, etc.).

```bash
curl -X PATCH "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "name": "Updated ASR Model Comparison",
    "description": "Updated description",
    "task_type": ["asr", "tts"],
    "languages": ["hi", "en", "ta"]
  }'
```

**Note**: Cannot update variants of a RUNNING experiment.

---

## 5. Update Experiment Status

Updates experiment status using actions: `start`, `stop`, `pause`, `resume`, `cancel`.

### Start Experiment (DRAFT → RUNNING)

```bash
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "action": "start"
  }'
```

### Stop Experiment (RUNNING → COMPLETED)

```bash
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "action": "stop"
  }'
```

### Pause Experiment (RUNNING → PAUSED)

```bash
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "action": "pause"
  }'
```

### Resume Experiment (PAUSED → RUNNING)

```bash
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "action": "resume"
  }'
```

### Cancel Experiment (Any non-RUNNING → CANCELLED)

```bash
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "action": "cancel"
  }'
```

---

## 6. Select Experiment Variant

Selects which variant to use for a given request. Used by services/gateway for routing.
When `user_id` is provided, the same user always gets the same variant (sticky assignment).

```bash
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/select-variant" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "task_type": "asr",
    "language": "hi",
    "request_id": "req-12345",
    "user_id": "2"
  }'
```

**Response Example**:
```json
{
  "experiment_id": "uuid",
  "variant_id": "uuid",
  "variant_name": "control",
  "service_id": "service-id",
  "model_id": "model-id",
  "model_version": "v1.0",
  "endpoint": "http://service:port",
  "api_key": "api-key",
  "is_experiment": true
}
```

If no matching experiment:
```json
{
  "is_experiment": false
}
```

---

## 7. Delete Experiment

Deletes an experiment (cannot delete RUNNING experiments).

```bash
curl -X DELETE "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
```

---

## Complete Test Workflow

Here's a complete workflow to test all functionalities:

```bash
# Set variables
export BASE_URL="http://localhost:8000"
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZW1haWwiOiJnZW9AZ21haWwuY29tIiwidXNlcm5hbWUiOiJnZW8iLCJleHAiOjE3OTkzODQ3NTgsInR5cGUiOiJhY2Nlc3MiLCJyb2xlcyI6WyJBRE1JTiJdfQ.UMwkHVhGPkkVJq5xZ0Xw4QOPrMimewNLqq_n06As05Q"

# Step 1: List existing services to get service IDs
echo "=== Step 1: List Services ==="
curl -X GET "${BASE_URL}/api/v1/model-management/services/" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.[] | {serviceId, name, modelId, modelVersion}'

# Step 2: Create an experiment (replace SERVICE_ID_1 and SERVICE_ID_2)
echo -e "\n=== Step 2: Create Experiment ==="
EXPERIMENT_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/model-management/experiments" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "name": "Test ASR Experiment",
    "description": "Testing A/B experiment functionality",
    "task_type": ["asr"],
    "languages": ["hi", "en"],
    "variants": [
      {
        "variant_name": "control",
        "service_id": "SERVICE_ID_1",
        "traffic_percentage": 50,
        "description": "Control variant"
      },
      {
        "variant_name": "variant-a",
        "service_id": "SERVICE_ID_2",
        "traffic_percentage": 50,
        "description": "Test variant"
      }
    ]
  }')

EXPERIMENT_ID=$(echo $EXPERIMENT_RESPONSE | jq -r '.id')
echo "Created experiment ID: ${EXPERIMENT_ID}"

# Step 3: Get experiment details
echo -e "\n=== Step 3: Get Experiment Details ==="
curl -X GET "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.'

# Step 4: List all experiments
echo -e "\n=== Step 4: List All Experiments ==="
curl -X GET "${BASE_URL}/api/v1/model-management/experiments" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.'

# Step 5: Start the experiment
echo -e "\n=== Step 5: Start Experiment ==="
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"action": "start"}' | jq '.'

# Step 6: Test variant selection (user_id gives same user => same variant)
echo -e "\n=== Step 6: Select Variant ==="
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/select-variant" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "task_type": "asr",
    "language": "hi",
    "request_id": "test-request-123",
    "user_id": "2"
  }' | jq '.'

# Step 7: Pause the experiment
echo -e "\n=== Step 7: Pause Experiment ==="
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"action": "pause"}' | jq '.'

# Step 8: Resume the experiment
echo -e "\n=== Step 8: Resume Experiment ==="
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"action": "resume"}' | jq '.'

# Step 9: Update experiment
echo -e "\n=== Step 9: Update Experiment ==="
curl -X PATCH "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "description": "Updated description after testing"
  }' | jq '.'

# Step 10: Stop the experiment
echo -e "\n=== Step 10: Stop Experiment ==="
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"action": "stop"}' | jq '.'

# Step 11: Delete the experiment
echo -e "\n=== Step 11: Delete Experiment ==="
curl -X DELETE "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}" \
  -H "Authorization: Bearer ${TOKEN}" -v
```

---

## Helper Script: Get Service IDs

Before creating an experiment, you need published service IDs. Use this to get them:

```bash
curl -X GET "${BASE_URL}/api/v1/model-management/services/?is_published=true" \
  -H "Authorization: Bearer ${TOKEN}" | \
  jq -r '.[] | "\(.serviceId) - \(.name) (Model: \(.modelId) v\(.modelVersion))"'
```

---

## Error Scenarios to Test

### 1. Invalid Traffic Percentage Sum
```bash
curl -X POST "${BASE_URL}/api/v1/model-management/experiments" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "name": "Invalid Experiment",
    "variants": [
      {"variant_name": "control", "service_id": "SERVICE_ID_1", "traffic_percentage": 30},
      {"variant_name": "variant-a", "service_id": "SERVICE_ID_2", "traffic_percentage": 60}
    ]
  }'
# Expected: Error - traffic percentages must sum to 100
```

### 2. Less Than 2 Variants
```bash
curl -X POST "${BASE_URL}/api/v1/model-management/experiments" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "name": "Invalid Experiment",
    "variants": [
      {"variant_name": "control", "service_id": "SERVICE_ID_1", "traffic_percentage": 100}
    ]
  }'
# Expected: Error - at least 2 variants required
```

### 3. Invalid Status Transition
```bash
# Try to stop a DRAFT experiment (should fail)
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"action": "stop"}'
# Expected: Error - cannot stop experiment in DRAFT status
```

### 4. Delete Running Experiment
```bash
# Start experiment first, then try to delete
curl -X POST "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"action": "start"}'

curl -X DELETE "${BASE_URL}/api/v1/model-management/experiments/${EXPERIMENT_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
# Expected: Error - cannot delete RUNNING experiment
```

---

## Notes

1. **Service IDs**: You must have at least 2 published services before creating experiments
2. **Traffic Percentages**: Must sum to exactly 100
3. **Status Transitions**: 
   - Only DRAFT experiments can be started
   - Only RUNNING experiments can be stopped or paused
   - Only PAUSED experiments can be resumed
   - Only non-RUNNING experiments can be deleted or cancelled
4. **Variant Selection**: Only RUNNING experiments route traffic
5. **Filters**: Experiments filter by task_type, languages, and date range

---

## Direct Service Access (Bypassing API Gateway)

If you want to test directly against the model-management-service:

```bash
export SERVICE_URL="http://localhost:8091"

# Create experiment
curl -X POST "${SERVICE_URL}/experiments" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{...}'

# List experiments
curl -X GET "${SERVICE_URL}/experiments" \
  -H "Authorization: Bearer ${TOKEN}"
```
