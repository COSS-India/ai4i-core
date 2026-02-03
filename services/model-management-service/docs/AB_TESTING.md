# A/B Testing for Models

This guide explains how to use the A/B testing feature in the Model Management Service to compare two model services.

## Overview

A/B testing allows you to:
- Compare a new model (treatment) against the current production model (control)
- Gradually roll out a new model by controlling the traffic percentage
- Make data-driven decisions about which model performs better

## Quick Start

### 1. Create an Experiment

```bash
curl -X POST http://model-management-service:8091/experiments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{
    "name": "nmt-indictrans-v2-test",
    "description": "Testing new IndicTrans v2 model for Hindi-English",
    "task_type": "nmt",
    "control_service_id": "abc123def456abc123def456abc12345",
    "treatment_service_id": "xyz789xyz789xyz789xyz789xyz78901",
    "treatment_percentage": 10
  }'
```

### 2. Start the Experiment

```bash
curl -X POST http://model-management-service:8091/experiments/{experiment_id}/start \
  -H "Authorization: Bearer <your-token>"
```

### 3. Monitor & Adjust Traffic

Increase traffic to treatment as confidence grows:

```bash
# Increase to 30%
curl -X PATCH http://model-management-service:8091/experiments/{experiment_id} \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"treatment_percentage": 30}'

# Then to 50%
curl -X PATCH http://model-management-service:8091/experiments/{experiment_id} \
  -d '{"treatment_percentage": 50}'

# Finally to 100%
curl -X PATCH http://model-management-service:8091/experiments/{experiment_id} \
  -d '{"treatment_percentage": 100}'
```

### 4. Stop the Experiment

```bash
curl -X POST http://model-management-service:8091/experiments/{experiment_id}/stop \
  -H "Authorization: Bearer <your-token>"
```

## API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/experiments` | Create a new experiment |
| `GET` | `/experiments` | List all experiments |
| `GET` | `/experiments/{id}` | Get experiment details |
| `PATCH` | `/experiments/{id}` | Update experiment (e.g., traffic %) |
| `DELETE` | `/experiments/{id}` | Delete experiment (DRAFT/STOPPED only) |
| `POST` | `/experiments/{id}/start` | Start experiment |
| `POST` | `/experiments/{id}/stop` | Stop experiment |
| `GET` | `/experiments/resolve/variant` | Resolve which variant to use |

### Create Experiment Request

```json
{
  "name": "string (required, unique)",
  "description": "string (optional)",
  "task_type": "string (required: asr, nmt, tts, etc.)",
  "control_service_id": "string (required)",
  "treatment_service_id": "string (required)",
  "treatment_percentage": "integer (0-100, default: 50)"
}
```

### Variant Resolution (For Inference Services)

```bash
GET /experiments/resolve/variant?task_type=nmt&user_id=user123
```

Response:
```json
{
  "service_id": "xyz789xyz789xyz789xyz789xyz78901",
  "variant": "treatment",
  "experiment_name": "nmt-indictrans-v2-test",
  "experiment_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Integration with Inference Services

### How to Integrate

Add this to your inference service before routing to a model:

```python
from utils.experiment_client import ExperimentClient

experiment_client = ExperimentClient(
    base_url=os.getenv("MODEL_MANAGEMENT_SERVICE_URL")
)

async def run_inference(request, auth_headers):
    # 1. Check for active A/B experiment
    exp_service_id, variant, experiment_name = await experiment_client.resolve_variant(
        task_type="nmt",  # or "asr", "tts", etc.
        user_id=request.user_id,
        tenant_id=request.tenant_id,
        auth_headers=auth_headers
    )
    
    # 2. Use experiment service_id if available, else use default
    service_id = exp_service_id or request.config.serviceId
    
    # 3. Get endpoint and run inference
    result = await run_model_inference(service_id, request)
    
    # 4. Tag metrics with experiment info
    record_metrics(
        latency_ms=latency,
        experiment=experiment_name or "none",
        variant=variant
    )
    
    return result
```

### Experiment Client Example

```python
# utils/experiment_client.py

import httpx
from typing import Optional, Tuple

class ExperimentClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def resolve_variant(
        self,
        task_type: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        auth_headers: dict = None
    ) -> Tuple[Optional[str], str, Optional[str]]:
        """
        Returns: (service_id, variant, experiment_name)
        service_id is None if no experiment is active
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/experiments/resolve/variant",
                    params={
                        "task_type": task_type,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                    },
                    headers=auth_headers,
                    timeout=2.0
                )
                if response.status_code == 200:
                    data = response.json()
                    service_id = data.get("service_id") or None
                    return (
                        service_id if service_id else None,
                        data.get("variant", "default"),
                        data.get("experiment_name")
                    )
        except Exception as e:
            logger.warning(f"Experiment resolution failed: {e}")
        
        return (None, "default", None)
```

## Metrics & Analysis

### Prometheus Metrics Labels

Add these labels to your existing metrics:

```python
INFERENCE_LATENCY.labels(
    service_id=service_id,
    experiment=experiment_name or "none",
    variant=variant,  # "control", "treatment", or "default"
).observe(latency_seconds)
```

### Grafana Queries

**Compare P95 Latency:**
```promql
histogram_quantile(0.95,
  sum(rate(inference_latency_seconds_bucket{experiment="nmt-indictrans-v2-test"}[5m])) 
  by (variant, le)
)
```

**Request Count by Variant:**
```promql
sum(rate(inference_total{experiment="nmt-indictrans-v2-test"}[5m])) by (variant)
```

**Error Rate Comparison:**
```promql
sum(rate(inference_total{experiment="nmt-indictrans-v2-test", status="error"}[5m])) by (variant)
/
sum(rate(inference_total{experiment="nmt-indictrans-v2-test"}[5m])) by (variant)
```

## Experiment Lifecycle

```
DRAFT ──(start)──▶ RUNNING ──(stop)──▶ STOPPED
  │                   │
  │                   │ (can update treatment_percentage)
  │                   │
  ▼                   ▼
(delete)           (delete)
```

### Rules

1. **Only one RUNNING experiment per task_type** - Stop the current experiment before starting a new one
2. **STOPPED experiments cannot be restarted** - Create a new experiment instead
3. **Only DRAFT and STOPPED experiments can be deleted**
4. **Traffic percentage can be updated while RUNNING** - Use this for gradual rollout

## Sticky Assignment

Users are consistently assigned to the same variant throughout an experiment:

- **Same user** always gets the same variant (based on `user_id` hash)
- Falls back to `tenant_id` if no `user_id`
- Falls back to `request_id` if neither
- This ensures consistent user experience

## Best Practices

1. **Start Small**: Begin with 5-10% traffic to treatment
2. **Monitor Closely**: Watch error rates and latency during initial rollout
3. **Increase Gradually**: 10% → 30% → 50% → 100%
4. **Define Success Metrics**: Know what you're measuring before starting
5. **Run Long Enough**: Ensure statistical significance (at least 1000+ requests per variant)
6. **Document Results**: Record learnings before deleting experiments
