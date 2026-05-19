"""
Client IP extraction for OpenTelemetry spans.

Extracts client IP from request headers (respecting proxy chains)
and adds to current OTel span for distributed tracing.
"""

import logging
from typing import Optional

from fastapi import Request

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False


def extract_client_ip(request: Request) -> str:
    """
    Extract client IP from request, checking proxy headers first.

    Priority order:
    1. X-Forwarded-For (first IP in chain)
    2. X-Real-IP (nginx)
    3. X-Client-IP (other proxies)
    4. request.client.host (direct connection)

    Args:
        request: FastAPI Request object

    Returns:
        Client IP address or "unknown"
    """
    # ✅ SIMPLIFIED: Check headers in priority order using a loop
    # REMOVED: Verbose debug logs listing all headers
    # REASON: Each header check has its own debug log; redundant to list all upfront
    for header_name in ["X-Forwarded-For", "X-Real-IP", "X-Client-IP"]:
        value = request.headers.get(header_name, "").split(",")[0].strip()
        if value:
            logger.debug(f"Using {header_name}: {value}")
            return value

    # Fallback to direct connection
    if request.client:
        return request.client.host

    logger.warning("No client IP found in request")
    return "unknown"


def add_ip_to_current_span(request: Request) -> None:
    """
    Add client IP to current OpenTelemetry span.

    ✅ JUSTIFICATION:
    - Only works if TRACING_AVAILABLE and current span exists
    - Silently fails if either condition is false (don't break request flow)
    """
    if not TRACING_AVAILABLE:
        return

    try:
        span = trace.get_current_span()
        if span and span.is_recording():
            ip = extract_client_ip(request)
            # ✅ SIMPLIFIED: Use single semantic attribute
            # REMOVED: Redundant "http.client_ip" attribute
            # REASON: "client.ip" is OTel standard; "http.client_ip" is redundant
            span.set_attribute("client.ip", ip)
    except Exception:
        logger.debug("Failed to add IP to span (non-critical)")
