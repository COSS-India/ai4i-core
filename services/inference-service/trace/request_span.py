"""
OpenTelemetry span helpers for the inference pipeline.

Provides a shared tracer instance and utilities for creating named spans
with context attributes (userId, tenantId) from ai4i_core.context.
"""

import time
import logging
from contextlib import asynccontextmanager, contextmanager

from opentelemetry import trace, context as otel_context
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)

# Shared tracer for the inference service
tracer = trace.get_tracer("inference-service")


def get_context_attributes() -> dict:
    """
    Resolve userId, tenantId, and the request correlation ID for span attributes
    from ai4i_core ContextVars.

    RequestMiddleware (ai4i_core.logging) populates these contextvars from the
    gateway-injected headers before handlers run; contextvars propagate into the
    handler task, so they are the single source of truth — no header re-reading.

    correlation_id must be captured here (request context) and stored as a span
    attribute so that KafkaSpanExporter can read it from the span later on the
    background exporter thread, where get_trace_id() would return None.

    Returns dict with available values (skips None).
    """
    attrs = {}
    try:
        from ai4i_core.context import get_user_id, get_tenant_id, get_trace_id, get_auth_type
        user_id = get_user_id()
        tenant_id = get_tenant_id()
        correlation_id = get_trace_id()
        auth_type = get_auth_type()
        if user_id:
            attrs["userId"] = user_id
        if tenant_id:
            attrs["tenantId"] = tenant_id
        if correlation_id:
            attrs["correlation_id"] = correlation_id
        if auth_type:
            attrs["authType"] = auth_type
    except Exception as e:
        logger.debug(f"Could not read context attributes: {e}")
    return attrs


def get_endpoint_path() -> str:
    """Read endpoint_path from ai4i_core ContextVars."""
    try:
        from ai4i_core.context import get_endpoint_path as _get_ep
        return _get_ep() or ""
    except Exception:
        return ""


def compute_total_time_ms(start_time: float) -> float:
    """Compute elapsed time in milliseconds from a time.time() start."""
    return round((time.time() - start_time) * 1000, 2)


# Ordered phase groups for the human-readable "TIMING" line. Sub-phases render
# in parentheses under their parent so the line mirrors the request tree. Only
# keys actually present are shown, so this stays correct as phases change.
_TIMING_TOP = [
    "resolve_ms", "validate_ms", "preprocess_ms", "run_inference_ms", "postprocess_ms",
]
_TIMING_SUB = {
    "resolve_ms": ["mms_http_ms"],
    "run_inference_ms": [
        "build_payload_ms", "input_tokens_ms", "triton_ms",
        "output_convert_ms", "output_tokens_ms",
    ],
}


def format_timing_summary(attrs: dict) -> str:
    """Build the one-line 'TIMING ...' summary from the merged phase attrs on
    the root request span (companion to the span JSON, for humans reading logs).
    """
    parts = [f"total={attrs.get('total_time_ms', 0)}ms"]
    for key in _TIMING_TOP:
        if key not in attrs:
            continue
        entry = f"{key[:-3]}={attrs[key]}"
        subs = [f"{s[:-3]}={attrs[s]}" for s in _TIMING_SUB.get(key, []) if s in attrs]
        if subs:
            entry += " (" + " ".join(subs) + ")"
        parts.append(entry)
    if "cache_hit" in attrs:
        parts.append(f"cache_hit={str(attrs['cache_hit']).lower()}")
    return "TIMING " + " ".join(parts)


def log_span_attributes(span_name: str, span, attributes: dict) -> None:
    """
    Log span attributes in OpenTelemetry standard JSON format.

    Uses the request correlation_id (seeded by RequestMiddleware from
    X-Correlation-ID) as context.trace_id so OpenSearch queries from
    platform-core correlate correctly. The OTel SDK trace ID is preserved
    as context.otel_trace_id for cross-service OTel joins.
    """
    import json
    try:
        span_context = span.get_span_context()
        correlation_id = attributes.get("correlation_id")
        otel_format = {
            "name": span_name,
            "context": {
                "trace_id": correlation_id or f"0x{span_context.trace_id:032x}",
                "otel_trace_id": f"0x{span_context.trace_id:032x}",
                "span_id": f"0x{span_context.span_id:016x}",
                "trace_state": str(span_context.trace_state or "")
            },
            "kind": "SpanKind.INTERNAL",
            "attributes": attributes
        }
        logger.info(json.dumps(otel_format))
    except Exception as e:
        logger.debug(f"Error logging span in OTel format: {e}")



@contextmanager
def traced_span(
    span_name: str,
    *,
    root: bool = False,
    classify_status: bool = False,
    mark_ok: bool = True,
    error_attrs=None,
):
    """
    THE span-lifecycle primitive: opens a span, captures start_time, yields a
    mutable attrs dict for the caller to enrich, and finalizes with
    total_time_ms plus success/error status. Every traced section (request,
    model, ai-inference) goes through here — never hand-roll
    `start_time = time.time()` + finalize again.

    Args:
        root: start with an empty otel context (parentID=null root span)
        classify_status: add status/status_code attrs (200 ok; 400 for
            ValueError, else 500 on failure)
        mark_ok: set OTel StatusCode.OK on success (request/model spans do;
            ai-inference historically leaves it UNSET — kept for exporter
            output parity)
        error_attrs: optional fn(attrs, exc) -> attrs to reshape the
            collected attrs on failure (e.g. zero token counts)
    """
    # Per-block phase timings ride the root span only — child spans (model,
    # ai-inference) carry their own total_time_ms and must not duplicate them.
    if root:
        from trace.phase_timer import start_root_phases
        start_root_phases()

    start_time = time.time()
    context = otel_context.Context() if root else None
    with tracer.start_as_current_span(span_name, context=context) as span:
        attrs: dict = {}
        try:
            yield attrs
        except Exception as e:
            if error_attrs is not None:
                attrs = error_attrs(attrs, e)
            attrs["total_time_ms"] = compute_total_time_ms(start_time)
            if classify_status:
                attrs["status"] = "failure"
                attrs["status_code"] = 400 if isinstance(e, ValueError) else 500
            finalize_span(span, attrs, error=e)
            raise
        else:
            attrs["total_time_ms"] = compute_total_time_ms(start_time)
            if classify_status:
                attrs.setdefault("status", "success")
                attrs.setdefault("status_code", 200)
            finalize_span(span, attrs, ok=mark_ok)


def finalize_span(span, attributes: dict, *, error=None, ok: bool = False) -> None:
    """
    Set attributes on a span and record its status.
    Single helper for the request/model/ai-inference span finalization.
    """
    for key, value in attributes.items():
        span.set_attribute(key, value)
    if error is not None:
        span.set_status(StatusCode.ERROR, str(error))
    elif ok:
        span.set_status(StatusCode.OK)


@asynccontextmanager
async def traced_inference(payload: dict, task_name: str, logger_: logging.Logger):
    """
    The 'ai-inference' span around an inference call, built on traced_span.

    Yields a mutable attrs dict pre-seeded with input_type; the wrapped code
    fills in input_tokens / output_tokens / output_type as they become known.
    On failure token counts are zeroed and the error is logged with traceback.

    Single definition shared by the base run_inference and TTS's override —
    keep span attribute changes here only.
    """
    from trace.span_attributes import get_input_type

    def _zero_tokens(attrs, exc):
        logger_.error(f"{task_name}: inference failed: {exc}", exc_info=True)
        attrs["input_tokens"] = 0
        attrs["output_tokens"] = 0
        return attrs

    with traced_span(
        "ai-inference", classify_status=True, mark_ok=False, error_attrs=_zero_tokens
    ) as attrs:
        # Seed correlation_id (and tenantId/authType) so KafkaSpanExporter uses
        # the same context.trace_id as the sibling request/model spans.  Without
        # this the ai-inference span lands in OpenSearch under the raw OTel trace
        # ID (0x…) rather than the correlation ID, making it invisible in the UI.
        attrs.update(get_context_attributes())
        attrs.update({
            "input_type": get_input_type(payload),
            "output_type": "unknown",
            "input_tokens": 0,
            "output_tokens": 0,
            # For trace/observability only — the PPU consumer's LLM/non-LLM
            # billing decision reads mm_services.task_type instead (via
            # get_service_pricing), not this span attribute.
            "task_type": task_name.lower(),
        })
        yield attrs
