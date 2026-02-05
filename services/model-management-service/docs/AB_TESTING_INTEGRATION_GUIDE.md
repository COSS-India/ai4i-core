# A/B Testing Integration Guide for Services

## Overview

This guide explains the **optimal way to integrate A/B testing** into service inference flows and **how to collect metrics** for experiment analysis.

## Integration Architecture

### Optimal Integration Point

The best place to integrate A/B testing is **in the service's model resolution step**, right before getting the Triton client. This ensures:

1. ✅ **Minimal code changes** - Single integration point per service
2. ✅ **Consistent behavior** - All services follow same pattern
3. ✅ **Transparent to business logic** - Inference code doesn't need to know about A/B testing
4. ✅ **Easy to disable** - Can be feature-flagged or removed easily

### Integration Flow

```
User Request
    ↓
Service Router (extracts task_type, language, service_id)
    ↓
[INTEGRATION POINT] Check for A/B Test Variant
    ├─→ If experiment active: Use variant's service_id, endpoint, model
    └─→ If no experiment: Use original service_id (default behavior)
    ↓
Get Triton Client (uses resolved service_id/endpoint)
    ↓
Run Inference
    ↓
[INTEGRATION POINT] Track Metrics (if experiment active)
    ↓
Return Response
```

## Implementation Pattern

### Step 1: Add A/B Testing Client Method

Add a method to `ModelManagementClient` to select variants:

**File:** `libs/ai4icore_model_management/ai4icore_model_management/client.py`

```python
async def select_experiment_variant(
    self,
    task_type: str,
    language: Optional[str] = None,
    request_id: Optional[str] = None,
    auth_headers: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Select an experiment variant for a given request.
    
    Args:
        task_type: Task type (e.g., "asr", "nmt", "tts")
        language: Optional language code (e.g., "hi", "en")
        request_id: Optional request ID for consistent routing
        auth_headers: Optional auth headers from incoming request
        
    Returns:
        Dictionary with variant details if experiment active, None otherwise
        {
            "experiment_id": "uuid",
            "variant_id": "uuid",
            "variant_name": "control",
            "service_id": "service-id",
            "model_id": "model-id",
            "model_version": "v1.0",
            "endpoint": "http://service:port",
            "api_key": "api-key",
            "is_experiment": True
        }
    """
    try:
        client = await self._get_client()
        url = f"{self.base_url}/experiments/select-variant"
        headers = self._get_headers(auth_headers)
        
        payload = {
            "task_type": task_type,
            "language": language,
            "request_id": request_id
        }
        
        response = await client.post(url, headers=headers, json=payload)
        
        if response.status_code == 404:
            return None
        
        response.raise_for_status()
        data = response.json()
        
        if not data.get("is_experiment", False):
            return None
        
        return data
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        logger.warning(f"Failed to select experiment variant: {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Error selecting experiment variant: {e}")
        return None
```

### Step 2: Create Service Helper Function

Create a reusable helper that services can use:

**File:** `libs/ai4icore_model_management/ai4icore_model_management/ab_testing.py` (new file)

```python
"""
A/B Testing Helper Functions for Service Integration
"""
from typing import Optional, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


async def resolve_service_with_ab_testing(
    model_management_client,
    original_service_id: str,
    task_type: str,
    language: Optional[str] = None,
    request_id: Optional[str] = None,
    auth_headers: Optional[Dict[str, str]] = None
) -> Tuple[str, Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """
    Resolve service details with A/B testing support.
    
    This function:
    1. Checks for active A/B test experiments
    2. Returns variant service details if experiment active
    3. Falls back to original service if no experiment
    
    Args:
        model_management_client: ModelManagementClient instance
        original_service_id: Original service ID from request
        task_type: Task type (e.g., "asr", "nmt", "tts")
        language: Optional language code
        request_id: Optional request ID for consistent routing
        auth_headers: Optional auth headers
        
    Returns:
        Tuple of:
        - resolved_service_id: Service ID to use (original or variant)
        - resolved_endpoint: Endpoint to use (None if using original service lookup)
        - resolved_model_name: Model name to use (None if using original service lookup)
        - experiment_info: Experiment details if active, None otherwise
            {
                "experiment_id": "uuid",
                "variant_id": "uuid",
                "variant_name": "control",
                "service_id": "service-id",
                ...
            }
    """
    # Check for A/B test variant
    variant_data = await model_management_client.select_experiment_variant(
        task_type=task_type,
        language=language,
        request_id=request_id,
        auth_headers=auth_headers
    )
    
    if variant_data and variant_data.get("is_experiment"):
        # Use variant's service details
        logger.info(
            f"A/B test active: Using variant '{variant_data.get('variant_name')}' "
            f"(experiment_id={variant_data.get('experiment_id')}, "
            f"service_id={variant_data.get('service_id')})"
        )
        return (
            variant_data.get("service_id"),
            variant_data.get("endpoint"),
            variant_data.get("model_id"),  # or model_name if available
            variant_data
        )
    else:
        # No experiment, use original service
        return (original_service_id, None, None, None)
```

### Step 3: Integrate into Service

**Example: NMT Service Integration**

**File:** `services/nmt-service/services/nmt_service.py`

```python
from ai4icore_model_management.ab_testing import resolve_service_with_ab_testing

class NMTService:
    # ... existing code ...
    
    async def run_inference(
        self,
        request: NMTInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> NMTInferenceResponse:
        """Run NMT inference on the given request"""
        start_time = time.time()
        request_id = None
        experiment_info = None  # Track experiment info for metrics
        
        with tracer.start_as_current_span("nmt.process_batch") as span:
            try:
                # Extract configuration
                original_service_id = request.config.serviceId
                source_lang = request.config.language.sourceLanguage
                target_lang = request.config.language.targetLanguage
                
                # [A/B TESTING INTEGRATION] Resolve service with A/B testing
                resolved_service_id, variant_endpoint, variant_model, experiment_info = \
                    await resolve_service_with_ab_testing(
                        model_management_client=self.model_management_client,
                        original_service_id=original_service_id,
                        task_type="nmt",  # or extract from service type
                        language=source_lang,  # Use source language for filtering
                        request_id=str(request_id) if request_id else None,
                        auth_headers=auth_headers
                    )
                
                # Use resolved service details
                if experiment_info:
                    # A/B test active - use variant's endpoint and model
                    service_id = resolved_service_id
                    endpoint = variant_endpoint
                    model_name = variant_model
                    
                    # Log experiment info
                    span.set_attribute("ab_test.experiment_id", experiment_info.get("experiment_id"))
                    span.set_attribute("ab_test.variant_id", experiment_info.get("variant_id"))
                    span.set_attribute("ab_test.variant_name", experiment_info.get("variant_name"))
                else:
                    # No experiment - use original service resolution
                    service_id = original_service_id
                    model_name = await self.get_model_name(service_id, auth_headers)
                    endpoint = None  # Will be resolved via get_triton_client
                
                # ... rest of inference logic ...
                
                # Get Triton client (will use variant endpoint if provided)
                if endpoint:
                    triton_client = TritonClient(triton_url=endpoint, api_key=experiment_info.get("api_key"))
                else:
                    triton_client = await self.get_triton_client(service_id, auth_headers)
                
                # Run inference
                response = triton_client.send_triton_request(...)
                
                # [METRICS TRACKING] Track experiment metrics if active
                if experiment_info:
                    await self._track_experiment_metrics(
                        experiment_info=experiment_info,
                        success=True,
                        latency_ms=int((time.time() - start_time) * 1000),
                        request_id=request_id
                    )
                
                return response
                
            except Exception as e:
                # [METRICS TRACKING] Track error if experiment active
                if experiment_info:
                    await self._track_experiment_metrics(
                        experiment_info=experiment_info,
                        success=False,
                        latency_ms=int((time.time() - start_time) * 1000),
                        request_id=request_id
                    )
                raise
```

### Step 4: Extract Task Type from Service

Different services need to extract `task_type` differently:

- **ASR Service**: `task_type = "asr"`
- **NMT Service**: `task_type = "nmt"`
- **TTS Service**: `task_type = "tts"`
- **OCR Service**: `task_type = "ocr"`
- **NER Service**: `task_type = "ner"`

You can:
1. **Hardcode** in each service (simplest)
2. **Extract from service metadata** (more flexible)
3. **Use service type from Model Management** (most dynamic)

**Recommended:** Hardcode for now, as it's explicit and clear.

## Metrics Collection

### Metrics to Collect

Based on the `experiment_metrics` table schema, collect:

1. **Request Count** - Total requests routed to variant
2. **Success Count** - Successful requests (HTTP 200-299)
3. **Error Count** - Failed requests (HTTP 400+ or exceptions)
4. **Latency Metrics**:
   - `avg_latency_ms` - Average latency
   - `p50_latency_ms` - 50th percentile
   - `p95_latency_ms` - 95th percentile
   - `p99_latency_ms` - 99th percentile
5. **Custom Metrics** (JSONB) - Service-specific metrics:
   - For ASR: `output_characters`, `output_words`
   - For NMT: `input_characters`, `output_characters`, `bleu_score` (if available)
   - For TTS: `input_characters`, `audio_length_seconds`

### Collection Strategy

**Option 1: Real-time Tracking (Recommended)**

Track metrics immediately after each request:

```python
async def _track_experiment_metrics(
    self,
    experiment_info: Dict[str, Any],
    success: bool,
    latency_ms: int,
    request_id: Optional[str] = None,
    custom_metrics: Optional[Dict[str, Any]] = None
):
    """Track experiment metrics for a single request"""
    try:
        # Call metrics tracking endpoint
        if self.model_management_client:
            await self.model_management_client.track_experiment_metric(
                experiment_id=experiment_info.get("experiment_id"),
                variant_id=experiment_info.get("variant_id"),
                success=success,
                latency_ms=latency_ms,
                custom_metrics=custom_metrics
            )
    except Exception as e:
        # Don't fail the request if metrics tracking fails
        logger.warning(f"Failed to track experiment metrics: {e}")
```

**Option 2: Batch Aggregation (For High Throughput)**

Collect metrics in memory and batch write periodically:

```python
# In service class
self._experiment_metrics_buffer: List[Dict] = []

async def _track_experiment_metrics(self, ...):
    """Add to buffer"""
    self._experiment_metrics_buffer.append({
        "experiment_id": experiment_info.get("experiment_id"),
        "variant_id": experiment_info.get("variant_id"),
        "success": success,
        "latency_ms": latency_ms,
        "custom_metrics": custom_metrics,
        "timestamp": time.time()
    })
    
    # Flush if buffer is large enough
    if len(self._experiment_metrics_buffer) >= 100:
        await self._flush_experiment_metrics()

async def _flush_experiment_metrics(self):
    """Batch write metrics to database"""
    # Aggregate and write to experiment_metrics table
    # Reset buffer
```

### Metrics API Endpoint

Add endpoint to Model Management Service:

**File:** `services/model-management-service/routers/router_experiments.py`

```python
@router_experiments_public.post("/track-metric", status_code=status.HTTP_204_NO_CONTENT)
async def track_experiment_metric_endpoint(payload: ExperimentMetricTrackRequest):
    """
    Track a single experiment metric.
    
    This endpoint is called by services after processing a request
    that was routed through an A/B test variant.
    """
    try:
        await track_experiment_metric(
            experiment_id=payload.experiment_id,
            variant_id=payload.variant_id,
            success=payload.success,
            latency_ms=payload.latency_ms,
            custom_metrics=payload.custom_metrics
        )
        return None
    except Exception as e:
        logger.exception("Error tracking experiment metric")
        # Don't fail - metrics are best effort
        return None
```

**File:** `services/model-management-service/db_operations.py`

```python
async def track_experiment_metric(
    experiment_id: str,
    variant_id: str,
    success: bool,
    latency_ms: int,
    custom_metrics: Optional[Dict[str, Any]] = None
):
    """
    Track a single experiment metric.
    
    This function:
    1. Finds or creates today's metric record
    2. Updates counters and latency percentiles
    3. Stores custom metrics
    """
    from datetime import datetime, date
    from sqlalchemy import func
    
    db: AsyncSession = AppDatabase()
    try:
        today = date.today()
        
        # Find existing metric record for today
        result = await db.execute(
            select(ExperimentMetrics).where(
                ExperimentMetrics.experiment_id == UUID(experiment_id),
                ExperimentMetrics.variant_id == UUID(variant_id),
                func.date(ExperimentMetrics.metric_date) == today
            )
        )
        metric = result.scalars().first()
        
        if not metric:
            # Create new metric record
            metric = ExperimentMetrics(
                experiment_id=UUID(experiment_id),
                variant_id=UUID(variant_id),
                metric_date=datetime.now(),
                request_count=0,
                success_count=0,
                error_count=0,
                custom_metrics={}
            )
            db.add(metric)
            await db.flush()
        
        # Update counters
        metric.request_count += 1
        if success:
            metric.success_count += 1
        else:
            metric.error_count += 1
        
        # Update latency (simplified - in production, use proper percentile calculation)
        # For now, just update average
        if metric.avg_latency_ms is None:
            metric.avg_latency_ms = latency_ms
        else:
            # Running average
            metric.avg_latency_ms = int(
                (metric.avg_latency_ms * (metric.request_count - 1) + latency_ms) / metric.request_count
            )
        
        # Update custom metrics
        if custom_metrics:
            if metric.custom_metrics is None:
                metric.custom_metrics = custom_metrics
            else:
                # Merge custom metrics
                metric.custom_metrics.update(custom_metrics)
        
        await db.commit()
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error tracking experiment metric: {e}")
        raise
    finally:
        await db.close()
```

### Metrics Retrieval Endpoint

Add endpoint to retrieve experiment metrics:

**File:** `services/model-management-service/routers/router_experiments.py`

```python
@router_experiments.get("/{experiment_id}/metrics", response_model=List[ExperimentMetricsResponse])
async def get_experiment_metrics_endpoint(
    experiment_id: str,
    variant_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None)
):
    """Get experiment metrics aggregated by date"""
    try:
        metrics = await get_experiment_metrics(
            experiment_id=experiment_id,
            variant_id=variant_id,
            start_date=start_date,
            end_date=end_date
        )
        return metrics
    except Exception as e:
        logger.exception(f"Error fetching experiment metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch metrics: {str(e)}"
        )
```

## Complete Integration Example

### ASR Service Integration

**File:** `services/asr-service/services/asr_service.py`

```python
from ai4icore_model_management.ab_testing import resolve_service_with_ab_testing

class ASRService:
    # ... existing code ...
    
    async def run_inference(
        self,
        request: ASRInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> ASRInferenceResponse:
        """Run ASR inference on audio inputs."""
        start_time = time.time()
        experiment_info = None
        
        try:
            # Extract configuration
            original_service_id = request.config.serviceId
            language = request.config.language.sourceLanguage
            
            # [A/B TESTING] Resolve service with A/B testing
            resolved_service_id, variant_endpoint, variant_model, experiment_info = \
                await resolve_service_with_ab_testing(
                    model_management_client=self.model_management_client,
                    original_service_id=original_service_id,
                    task_type="asr",
                    language=language,
                    request_id=str(request_id) if request_id else None,
                    auth_headers=None  # Add if available
                )
            
            # Use resolved service
            service_id = resolved_service_id
            model_name = variant_model if variant_model else self.resolved_model_name
            
            # ... existing inference logic ...
            
            # Calculate output metrics
            total_output_characters = sum(len(output.source) for output in response.output)
            total_output_words = sum(len(output.source.split()) for output in response.output)
            
            # [METRICS] Track experiment metrics
            if experiment_info:
                await self._track_experiment_metrics(
                    experiment_info=experiment_info,
                    success=True,
                    latency_ms=int((time.time() - start_time) * 1000),
                    custom_metrics={
                        "output_characters": total_output_characters,
                        "output_words": total_output_words
                    }
                )
            
            return response
            
        except Exception as e:
            # [METRICS] Track error
            if experiment_info:
                await self._track_experiment_metrics(
                    experiment_info=experiment_info,
                    success=False,
                    latency_ms=int((time.time() - start_time) * 1000)
                )
            raise
```

## Best Practices

1. **Fail Gracefully**: If A/B testing check fails, fall back to original service
2. **Don't Block**: Metrics tracking should never block the request
3. **Cache Variant Selection**: Consider caching variant selection for a few seconds to reduce API calls
4. **Log Experiment Activity**: Log when requests are routed through experiments for debugging
5. **Monitor Performance**: Track the overhead of A/B testing checks

## Testing

1. **Unit Tests**: Test variant selection logic
2. **Integration Tests**: Test full inference flow with experiments
3. **Load Tests**: Verify metrics collection doesn't impact performance

## Rollout Plan

1. **Phase 1**: Add A/B testing client method to `ModelManagementClient`
2. **Phase 2**: Create helper function and integrate into one service (e.g., NMT)
3. **Phase 3**: Add metrics tracking endpoint and collection
4. **Phase 4**: Integrate into remaining services
5. **Phase 5**: Add metrics visualization/analytics
