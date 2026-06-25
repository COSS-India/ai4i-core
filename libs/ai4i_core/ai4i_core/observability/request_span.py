"""
OpenTelemetry span helpers for the inference pipeline.

Provides a shared tracer instance and utilities for creating named spans.
Context attributes (userId, tenantId, endpoint_path) are read via
ai4i_core.context — import get_context_attributes / get_endpoint_path from
there rather than from this module.
"""

import logging
import time
from contextlib import asynccontextmanager, contextmanager

from opentelemetry import trace, context as otel_context
from opentelemetry.trace import StatusCode

from ai4i_core.observability.utils import compute_total_time_ms

logger = logging.getLogger(__name__)

# Shared tracer for the inference service
tracer = trace.get_tracer("inference-service")


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
            finalize_span(span, span_name, attrs, error=e)
            raise
        else:
            attrs["total_time_ms"] = compute_total_time_ms(start_time)
            if classify_status:
                attrs.setdefault("status", "success")
                attrs.setdefault("status_code", 200)
            finalize_span(span, span_name, attrs, ok=mark_ok)


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
        attrs.update({
            "input_type": get_input_type(payload),
            "output_type": "unknown",
            "input_tokens": 0,
            "output_tokens": 0,
        })
        yield attrs
