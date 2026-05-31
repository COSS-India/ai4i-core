"""
Lightweight tracing module for inference service.

Provides utilities to:
- Detect input/output modality types (text, audio, image)
- Compute metrics (token counts, payload sizes)
- Enrich OpenTelemetry spans with inference-specific attributes
- Access tenant/user context from ContextVars

No external telemetry dependencies—uses OpenTelemetry SDK directly.
"""
