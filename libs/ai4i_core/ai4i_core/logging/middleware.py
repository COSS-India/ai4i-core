"""
Request middleware — correlation ID + structured request logging in one pass.

Add this as the outermost middleware (last call to app.add_middleware) so it
runs first on every request.
"""

import re
import time
import logging
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_default_config
from ai4i_core.context import (
    generate_trace_id,
    set_api_key_id,
    set_auth_type,
    set_tenant_id,
    set_tier_id,
    set_trace_id,
)

_HEX32 = re.compile(r"^[0-9a-f]{32}$")

logger = logging.getLogger(__name__)


def _to_trace_id(raw: str) -> Optional[str]:
    """Normalise a header value to 32-hex. Returns None if the value is not usable."""
    normalized = raw.strip().replace("-", "").lower()
    return normalized if _HEX32.match(normalized) else None


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

        # Seed tenant_id from the gateway-injected X-Tenant-ID header (set by
        # auth-service /validate after verifying the bearer token; the gateway
        # forwards it upstream). Must happen before call_next so downstream
        # middlewares (observability, etc.) and handlers can read it from the
        # contextvar / request.state. HTTP header names are case-insensitive,
        # so this matches X-Tenant-Id / X-Tenant-ID / x-tenant-id.
        tenant_id = (request.headers.get("X-Tenant-Id") or "").strip()
        if tenant_id:
            set_tenant_id(tenant_id)
            request.state.tenant_id = tenant_id

        auth_type = (request.headers.get("X-Auth-Type") or "").strip()
        if auth_type:
            set_auth_type(auth_type)

        api_key_id = (request.headers.get("X-API-Key-ID") or "").strip()
        if api_key_id:
            set_api_key_id(api_key_id)

        tier_id = (request.headers.get("X-Tier-ID") or "").strip()
        if tier_id:
            set_tier_id(tier_id)

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
