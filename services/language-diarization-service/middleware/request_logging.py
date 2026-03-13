"""
Language Diarization service request logging middleware.

Extends ServiceRequestLoggingMiddleware with service-specific enrichment
(operation marker for successful inference calls).
"""

from fastapi import Request, Response

from ai4icore_logging import ServiceRequestLoggingMiddleware


def _extra_context(request: Request, response: Response):
    path = request.url.path or ""
    status_code = response.status_code
    if path.endswith("/inference") and 200 <= status_code < 300:
        return {
            "operation": "language_diarization.inference",
            "success": True,
        }
    return {}


class RequestLoggingMiddleware(ServiceRequestLoggingMiddleware):
    def __init__(self, app):
        super().__init__(app, extra_context_getter=_extra_context)


__all__ = ["RequestLoggingMiddleware"]

