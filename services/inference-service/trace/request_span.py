"""
OpenTelemetry span helpers for the inference pipeline.

Provides a shared tracer instance and utilities for creating named spans
with context attributes (userId, tenantId) from ai4icore_core.context.
"""

import time
import logging
from contextlib import asynccontextmanager

from opentelemetry import trace
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)

# Shared tracer for the inference service
tracer = trace.get_tracer("inference-service")


def get_context_attributes() -> dict:
    """
    Resolve userId and tenantId for span attributes from ai4icore_core ContextVars.

    RequestMiddleware (ai4icore_core.logging) populates these contextvars from
    the gateway-injected X-Tenant-Id / X-User-ID headers before handlers run;
    contextvars set in middleware propagate into the handler task, so they are
    the single source of truth here — no header re-reading.

    Returns dict with available values (skips None).
    """
    attrs = {}
    try:
        from ai4icore_core.context import get_user_id, get_tenant_id
        user_id = get_user_id()
        tenant_id = get_tenant_id()
        if user_id:
            attrs["userId"] = user_id
        if tenant_id:
            attrs["tenantId"] = tenant_id
    except Exception as e:
        logger.debug(f"Could not read context attributes: {e}")
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


def finalize_span(span, span_name: str, attributes: dict, *, error=None, ok: bool = False) -> None:
    """
    Set attributes on a span, record its status, and emit the OTel-format log line.
    Single helper for the request/model/ai-inference span finalization that was
    previously copy-pasted at each site.
    """
    for key, value in attributes.items():
        span.set_attribute(key, value)
    if error is not None:
        span.set_status(StatusCode.ERROR, str(error))
    elif ok:
        span.set_status(StatusCode.OK)
    log_span_attributes(span_name, span, attributes)


@asynccontextmanager
async def traced_inference(payload: dict, task_name: str, logger_: logging.Logger):
    """
    Own the 'ai-inference' span lifecycle around an inference call.

    Yields a mutable attrs dict pre-seeded with input_type; the wrapped code
    fills in input_tokens / output_tokens / output_type as they become known.
    On success the collected attrs are recorded with status 200; on failure
    token counts are zeroed and status_code is 400 for ValueError (bad request
    input) or 500 otherwise.

    Single definition shared by the text/image base, the audio base, and TTS —
    keep span attribute changes here only.
    """
    from trace.span_attributes import get_input_type

    start_time = time.time()
    with tracer.start_as_current_span("ai-inference") as span:
        ctx = {
            "input_type": get_input_type(payload),
            "output_type": "unknown",
            "input_tokens": 0,
            "output_tokens": 0,
        }
        try:
            yield ctx
        except Exception as e:
            logger_.error(f"{task_name}: inference failed: {e}", exc_info=True)
            finalize_span(span, "ai-inference", {
                "total_time_ms": compute_total_time_ms(start_time),
                "input_tokens": 0,
                "output_tokens": 0,
                "input_type": ctx["input_type"],
                "output_type": ctx["output_type"],
                "status": "failure",
                "status_code": 400 if isinstance(e, ValueError) else 500,
            }, error=e)
            raise
        else:
            finalize_span(span, "ai-inference", {
                "total_time_ms": compute_total_time_ms(start_time),
                "input_tokens": ctx["input_tokens"],
                "output_tokens": ctx["output_tokens"],
                "input_type": ctx["input_type"],
                "output_type": ctx["output_type"],
                "status": "success",
                "status_code": 200,
            })
