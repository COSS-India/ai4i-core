"""Which upstream failures move a request to the Application's fallback service.

Only "the model server can't be reached / failed on its side" does: timeouts,
connection errors and 5xx. Anything the client caused (invalid input, a 4xx,
an unknown or unpublished serviceId, a Tier denial) is returned as is.
"""

from typing import List

import httpx


class UpstreamUnavailableError(RuntimeError):
    """The model server timed out, was unreachable, or answered 5xx.

    Still a RuntimeError, so http_status_for maps it to 502 when no fallback
    is configured — exactly what the client got before fallbacks existed.
    """


class AllServicesUnavailableError(ConnectionError):
    """The requested service and every configured fallback failed (503)."""

    def __init__(self, service_id: str, tried: List[str]):
        super().__init__(
            f"Service '{service_id}' and its fallback service(s) are unavailable (tried: {', '.join(tried)})"
        )


def is_unavailable(exc: BaseException) -> bool:
    """Timeout, connection error (httpx.TransportError covers both) or 5xx."""
    return isinstance(exc, httpx.TransportError) or (
        isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500
    )
