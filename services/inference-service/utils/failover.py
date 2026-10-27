"""Which inference failures move a request on to a fallback service.

Only "the model server can't be reached / failed on its side" does:
timeouts, connection errors and 5xx from Triton or the LLM upstream. Anything
the client caused — invalid input, a 4xx from the upstream, auth, quota,
rate limit, an unknown or unpublished serviceId — is returned as is.

The Triton call marks those failures by raising UpstreamUnavailableError (a
RuntimeError, so http_status_for still maps it to 502 when no fallback is
configured). Downloading a user-supplied audio/image URI raises plain httpx
errors earlier in the pipeline and is deliberately NOT marked: an unreachable
input URL is the client's problem, not the model's.
"""

from typing import List, Optional, Tuple

import httpx


class UpstreamUnavailableError(RuntimeError):
    """The model server timed out, was unreachable, or answered 5xx."""

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


class AllServicesUnavailableError(ConnectionError):
    """The requested service and every configured fallback failed."""

    def __init__(self, requested_service_id: str, attempts: List[Tuple[str, str]]):
        self.requested_service_id = requested_service_id
        self.attempts = attempts
        tried = ", ".join(sid for sid, _ in attempts)
        super().__init__(f"Service '{requested_service_id}' and its fallback service(s) are unavailable (tried: {tried})")

    def to_openai_error(self) -> dict:
        """The LLM routes' shape — OpenAI clients read ``error.message``."""
        return {"error": {"message": str(self), "type": "all_services_unavailable"}}

    def to_body(self) -> dict:
        """The Triton routes' HTTPException ``detail``."""
        return {"code": "ALL_SERVICES_UNAVAILABLE", "message": str(self)}


def failover_reason(exc: BaseException) -> Optional[str]:
    """The reason to try the next service, or None when ``exc`` must be
    returned to the client unchanged. Walks the ``raise ... from`` chain."""
    cause: Optional[BaseException] = exc
    for _ in range(16):
        if cause is None:
            return None
        if isinstance(cause, UpstreamUnavailableError):
            return cause.reason
        cause = cause.__cause__
    return None


def classify_upstream_failure(
    exc: Optional[BaseException] = None, status_code: Optional[int] = None
) -> Optional[str]:
    """Reason for an httpx failure (``exc``) or an upstream HTTP status, or
    None if it's a client-side error. Shared by the Triton call and the LLM
    proxy."""
    if status_code is not None:
        return "upstream_5xx" if status_code >= 500 else None
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError):
        return "unreachable"
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return "upstream_5xx"
    return None
