"""
Trace Module Documentation

A lightweight distributed tracing module for the inference service that enriches
OpenTelemetry spans with inference-specific attributes without using complex
telemetry utilities.

## Overview

The trace module provides utilities to:
1. Detect input/output modality (text, audio, image)
2. Compute inference metrics (token counts, payload sizes)
3. Enrich OpenTelemetry spans with tracing attributes
4. Access tenant/user context from ContextVars (set by middleware from JWT)

## Components

### 1. span_attributes.py
Core functions for attribute computation:

- `get_input_type(payload)` → "text" | "audio" | "image" | "unknown"
  Detects modality by checking payload['input'], payload['audio'], payload['image']

- `get_output_type(response_data)` → "text" | "audio" | "image" | "unknown"
  Inspects response structure and field names to determine output modality

- `count_input_tokens(input_items, input_type)` → int
  Estimates token count based on modality:
  - Text: word split (len(text.split()))
  - Audio: samples / 16000 * 100
  - Image: base64 length / 1000

- `count_output_tokens(response_data, output_type)` → int
  Estimates output token count similarly

- `get_payload_size_kb(data)` → float
  Computes JSON serialization size in KB

### 2. inference_span.py
Span enrichment functions that interact with current OpenTelemetry span:

- `set_input_span_attributes(payload, input_items, config)` → None
  Called before Triton inference. Sets attributes:
  - input_type: Detected modality
  - input_size_kb: Payload size
  - input_tokens: Estimated token count
  - tenantId: From ContextVar (JWT via middleware)
  - userId: From ContextVar (JWT via middleware)

- `set_output_span_attributes(response_data, status, status_code)` → None
  Called after Triton inference. Sets attributes:
  - output_type: Detected modality
  - output_size_kb: Payload size
  - output_tokens: Estimated token count
  - status: "success" or "failure"
  - status_code: HTTP status code

## Integration with BaseTaskService

In `execute_triton_inference()`:

```python
# Before Triton call
set_input_span_attributes(payload, input_items, config_data)

# ... Triton inference ...

# After Triton call (success path)
set_output_span_attributes(response_data, status="success", status_code=200)

# In exception handler
set_output_span_attributes([], status="failure", status_code=500)
```

The `@async_trace_stage("ai_inference")` decorator on `execute_triton_inference()`
automatically creates the OpenTelemetry span. The span enrichment functions
get the current span via `trace.get_current_span()` and add attributes.

## ContextVar Integration

Tenant/user context is automatically populated by middleware from JWT claims:

1. **TraceIDMiddleware** sets trace_id and endpoint_path
2. **ObservabilityMiddleware** sets tenant_id and user_id from JWT

The span functions read these via:
- `get_tenant_id()` from ai4i_core.context
- `get_user_id()` from ai4i_core.context

No additional setup needed—middleware automatically handles context propagation.

## Error Handling

All functions return safe defaults on error to prevent trace enrichment from
breaking inference:
- `count_input_tokens()` returns 0
- `count_output_tokens()` returns 0
- `get_payload_size_kb()` returns 0.0
- `get_input_type()` and `get_output_type()` return "unknown"
- Context var reads return None gracefully

Warnings are logged but no exceptions are raised.

## Example Trace Structure

When a request flows through the service, the trace shows:

```
request (span)
  └─ model (span)
       └─ ai_inference (span)  ← enriched with:
            - input_type: "text"
            - input_size_kb: 2.5
            - input_tokens: 150
            - tenantId: "org-123"
            - userId: "user-456"
            - status: "success"
            - output_type: "text"
            - output_size_kb: 3.2
            - output_tokens: 120
            - status_code: 200
```

## Dependencies

- opentelemetry-api (for `trace.get_current_span()`)
- ai4i_core.context (for tenant/user context vars)

No additional external dependencies.

## Future Enhancements

1. **Tokenizer Integration**: Use HuggingFace tokenizers for more accurate counts
2. **Triton Response Metadata**: Extract token counts from Triton response if available
3. **Custom Attributes**: Allow services to register modality-specific attributes
4. **Span Links**: Link to parent spans for better hierarchy tracking
"""

# This file serves as documentation only. Import from the actual modules instead.
