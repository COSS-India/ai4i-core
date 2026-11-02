"""HTTP status for an orchestration failure.

One mapping for both the response (routes/inference.py `_http_error_for`) and
the Triton "request" span (orchestrator.py), so the span records the status
the client actually got. The billing consumer writes each API-key request's
usage_events row from that span, and the Usage Dashboard counts failures by
its status_code.
"""
from typing import Optional

from utils.failover import AllServicesUnavailableError


def _cause_chain(exc: BaseException) -> list[BaseException]:
    chain = []
    cause: Optional[BaseException] = exc
    while cause is not None and len(chain) < 16:
        chain.append(cause)
        cause = cause.__cause__
    return chain


def http_status_for(exc: BaseException) -> int:
    """Walks the exception __cause__ chain (raised with `from exc` throughout)
    so the original error classifies the response. Builtin exceptions only:
      PermissionError     → 403 (tier gate)
      ValueError          → 400 (validation)
      NotImplementedError → 501 (unimplemented task, e.g. PII)
      LookupError         → 404 (unknown serviceId; exact type only)
      AllServicesUnavailableError → 503 (requested service and every fallback failed)
      ConnectionError     → 502 (MMS / Triton unreachable)
      RuntimeError        → 502 (server-side config / backend mismatch)
      anything else       → 500
    """
    chain = _cause_chain(exc)
    for e in chain:
        if isinstance(e, AllServicesUnavailableError):
            return 503
        if isinstance(e, PermissionError):
            return 403
        if isinstance(e, ValueError):
            return 400
        if isinstance(e, NotImplementedError):
            return 501
        # exact type: KeyError/IndexError are LookupError subclasses but are
        # programming errors, not not-found semantics — they must stay 500
        if type(e) is LookupError:
            return 404
    for e in chain:
        if isinstance(e, (RuntimeError, ConnectionError)):
            return 502
    return 500
