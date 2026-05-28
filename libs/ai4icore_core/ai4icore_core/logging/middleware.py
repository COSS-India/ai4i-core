"""
Request middleware — correlation ID + structured request logging in one pass.

Add this as the outermost middleware (last call to app.add_middleware) so it
runs first on every request.
"""

import re
import time
import logging
from typing import Optional

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_default_config
from ai4icore_core.context import (
    generate_trace_id,
    set_tenant_id,
    set_trace_id,
)

_HEX32 = re.compile(r"^[0-9a-f]{32}$")

logger = logging.getLogger(__name__)


def _to_trace_id(raw: str) -> Optional[str]:
    """Normalise a header value to 32-hex. Returns None if the value is not usable."""
    normalized = raw.strip().replace("-", "").lower()
    return normalized if _HEX32.match(normalized) else None


def _extract_tenant_id(request: Request) -> Optional[str]:
    """Pull tenant_id from a Bearer JWT (unverified — labeling only).

    The signature is *not* verified here; tenant_id is used only for log
    enrichment and metric labeling. Auth/permission enforcement is the
    gateway's job. Returns None when no usable claim is present.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    try:
        claims = jwt.decode(auth_header[7:], options={"verify_signature": False})
    except Exception:
        return None
    tid = claims.get("tenant_id")
    return str(tid) if tid not in (None, "") else None


class RequestMiddleware(BaseHTTPMiddleware):
    """
    Seeds the trace ID from X-Correlation-ID (or generates one), then logs
    one structured JSON line per request after the response is ready.

    Skips health checks, metrics scrapes, and OPTIONS pre-flights by default
    (controlled via EXCLUDE_* env vars). Skips 4xx responses — the API gateway
    logs those.
    """

    def __init__(self, app, header_name: str = "X-Correlation-ID"):
        super().__init__(app)
        self.header_name = header_name
        cfg = get_default_config()
        self.exclude_health = cfg.exclude_health_logs
        self.exclude_metrics = cfg.exclude_metrics_logs
        self.exclude_options = cfg.exclude_options_logs

    def _should_skip(self, method: str, path: str) -> bool:
        p = path.lower()
        if self.exclude_options and method.upper() == "OPTIONS":
            return True
        if self.exclude_health and "/health" in p:
            return True
        if self.exclude_metrics and "/metrics" in p:
            return True
        return False

    async def dispatch(self, request: Request, call_next):
        # Seed trace ID — must happen before call_next so all downstream
        # log calls (route handlers, service layer) carry the same trace ID.
        raw = request.headers.get(self.header_name, "")
        trace_id = (_to_trace_id(raw) if raw else None) or generate_trace_id()
        set_trace_id(trace_id)
        request.state.correlation_id = trace_id

        # Seed tenant_id from the JWT (unverified — labeling only). Must
        # happen before call_next so downstream middlewares (observability,
        # etc.) and handlers can read it from the contextvar / request.state
        # rather than each re-decoding the token.
        tenant_id = _extract_tenant_id(request)
        if tenant_id is not None:
            set_tenant_id(tenant_id)
            request.state.tenant_id = tenant_id

        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        response.headers[self.header_name] = trace_id
        response.headers["X-Process-Time"] = f"{duration_ms / 1000:.3f}"

        status = response.status_code

        if self._should_skip(request.method, request.url.path):
            return response

        # 4xx are logged at the gateway level — skip them here to avoid duplicates.
        if 400 <= status < 500:
            return response

        ctx = {
            "method": request.method,
            "path": request.url.path,
            "status_code": status,
            "duration_ms": round(duration_ms, 2),
            "client_ip": request.client.host if request.client else "unknown",
        }

        # Enrich with identity fields set by upstream auth/identity middleware.
        for field in ("user_id", "tenant_id", "organization"):
            value = getattr(request.state, field, None)
            if value:
                ctx[field] = value

        msg = f"{request.method} {request.url.path} {status}"
        if status >= 500:
            logger.error(msg, extra={"context": ctx})
        else:
            logger.info(msg, extra={"context": ctx})

        return response
