"""
OpenTelemetry span helpers for the inference pipeline.

Provides a shared tracer instance and utilities for creating named spans
with context attributes (userId, tenantId) from ai4icore_core.context.
"""

import time
import logging
from typing import Optional

from opentelemetry import trace, context as otel_context
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)

# Shared tracer for the inference service
tracer = trace.get_tracer("inference-service")


def get_context_attributes(request=None) -> dict:
    """
    Resolve userId and tenantId for span attributes.

    Prefers the gateway-injected request headers (X-Tenant-Id / X-User-ID) when a
    request is provided, falling back to the ai4icore_core ContextVars. Reading the
    headers directly is robust against Starlette BaseHTTPMiddleware not propagating
    the ContextVar set in RequestMiddleware into the endpoint task — which would
    otherwise leave spans without tenantId even though the log envelope has it.

    Returns dict with available values (skips None).
    """
    attrs = {}
    user_id = tenant_id = None
    try:
        from ai4icore_core.context import get_user_id, get_tenant_id
        user_id = get_user_id()
        tenant_id = get_tenant_id()
    except Exception as e:
        logger.debug(f"Could not read context attributes: {e}")

    # Request headers take precedence — same scope the span is built in.
    if request is not None:
        try:
            tenant_id = request.headers.get("X-Tenant-Id") or tenant_id
            user_id = request.headers.get("X-User-ID") or user_id
        except Exception as e:
            logger.debug(f"Could not read context headers: {e}")

    if user_id:
        attrs["userId"] = user_id
    if tenant_id:
        attrs["tenantId"] = tenant_id
    return attrs


def get_endpoint_path() -> str:
    """Read endpoint_path from ai4icore_core ContextVars."""
    try:
        from ai4icore_core.context import get_endpoint_path as _get_ep
        return _get_ep() or ""
    except Exception:
        return ""


def compute_total_time_ms(start_time: float) -> float:
    """Compute elapsed time in milliseconds from a time.time() start."""
    return round((time.time() - start_time) * 1000, 2)


def log_span_attributes(span_name: str, span, attributes: dict) -> None:
    """
    Log span attributes in OpenTelemetry standard JSON format.
    Reuses the same format as inference_span._log_span_attributes.
    """
    import json
    try:
        span_context = span.get_span_context()
        otel_format = {
            "name": span_name,
            "context": {
                "trace_id": f"0x{span_context.trace_id:032x}",
                "span_id": f"0x{span_context.span_id:016x}",
                "trace_state": str(span_context.trace_state or "")
            },
            "kind": "SpanKind.INTERNAL",
            "attributes": attributes
        }
        logger.info(json.dumps(otel_format))
    except Exception as e:
        logger.debug(f"Error logging span in OTel format: {e}")
