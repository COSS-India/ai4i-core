"""
Distributed trace context propagation for multi-service flows.

Propagates trace ID across HTTP requests so spans from different services
are linked together in a single distributed trace.

Example: OCR Service → NMT Service
  1. OCR service receives request, sets trace_id in context
  2. OCR calls NMT with X-Trace-ID header
  3. NMT extracts trace_id from header, sets it in context
  4. Both services' spans share same trace_id
"""

import logging
from typing import Dict, Optional

from ai4icore_core.context import get_trace_id, set_trace_id, generate_trace_id

logger = logging.getLogger(__name__)

# HTTP header names for trace context propagation
TRACE_ID_HEADER = "X-Trace-ID"
PARENT_SPAN_ID_HEADER = "X-Parent-Span-ID"
SPAN_ID_HEADER = "X-Span-ID"


def extract_trace_context(headers: Dict[str, str]) -> Dict[str, Optional[str]]:
    """
    Extract trace context from HTTP headers.

    Args:
        headers: HTTP request headers dict

    Returns:
        Dict with trace_id, span_id, parent_span_id
    """
    trace_id = headers.get(TRACE_ID_HEADER)
    span_id = headers.get(SPAN_ID_HEADER)
    parent_span_id = headers.get(PARENT_SPAN_ID_HEADER)

    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
    }


def inject_trace_context() -> Dict[str, str]:
    """
    Inject trace context into HTTP headers.

    Returns:
        Dict with headers to add to outgoing requests
    """
    trace_id = get_trace_id()
    
    headers = {}
    if trace_id:
        headers[TRACE_ID_HEADER] = trace_id

    return headers


def initialize_trace_context(headers: Dict[str, str]) -> str:
    """
    Initialize trace context from incoming request headers.

    If X-Trace-ID header exists, use it. Otherwise, generate a new one.

    Args:
        headers: HTTP request headers dict

    Returns:
        The trace_id that was set
    """
    context = extract_trace_context(headers)
    trace_id = context.get("trace_id")

    if not trace_id:
        trace_id = generate_trace_id()
        logger.debug(f"Generated new trace_id: {trace_id}")
    else:
        logger.debug(f"Using propagated trace_id: {trace_id}")

    set_trace_id(trace_id)
    return trace_id


def get_current_trace_id() -> str:
    """Get the current trace ID, generating one if needed."""
    trace_id = get_trace_id()
    if not trace_id:
        trace_id = generate_trace_id()
        set_trace_id(trace_id)
    return trace_id