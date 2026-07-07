"""Read tracing attributes injected by ObservabilityMiddleware."""

from typing import Any, Dict, Optional

from fastapi import Request

from ai4i_core.observability.tracing_headers import (
    TRACING_HEADER_PREFIX,
    read_tracing_headers_from_request,
)


def get_tracing_attributes(request: Optional[Request] = None) -> Dict[str, Any]:
    """Return pre-computed payload attributes from ``X-Tracing-*`` headers."""
    return read_tracing_headers_from_request(request)
