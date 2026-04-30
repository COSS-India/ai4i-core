"""
Generic request/response logging middleware for AI4ICore services.

Goal:
- One consistent structured log line per request (or per configured subset),
  enriched with correlation_id, trace_id, organization, tenant_id, etc.
- Avoid per-service copy/paste while keeping behavior configurable via env vars.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional, Set

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ai4icore_env import app_env

from .logger import get_logger
from .middleware import get_correlation_id

try:
    from opentelemetry import trace

    TRACING_AVAILABLE = True
except Exception:
    TRACING_AVAILABLE = False


def _parse_bool_env(name: str, default: str = "false") -> bool:
    raw = getattr(app_env, name.lower(), default)
    return bool(raw) if isinstance(raw, bool) else str(raw).lower().strip() in ("true", "1", "yes", "on")


def _parse_allowed_levels_env(raw: str) -> Set[int]:
    # raw example: "DEBUG,INFO,WARNING,ERROR"
    allowed: Set[int] = set()
    for level_str in (s.strip().upper() for s in (raw or "").split(",")):
        if not level_str:
            continue
        level_val = getattr(logging, level_str, None)
        if isinstance(level_val, int):
            allowed.add(level_val)
    return allowed


def _normalize_path_for_match(path: str) -> str:
    normalized = (path or "").split("?")[0].strip().lower()
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized or "/"


def _parse_csv_paths_env(raw: str) -> Set[str]:
    paths: Set[str] = set()
    for item in (s.strip() for s in (raw or "").split(",")):
        if not item:
            continue
        normalized = _normalize_path_for_match(item)
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        paths.add(normalized)
    return paths


class ServiceRequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Generic request logging middleware used by services.

    Env vars supported:
    - EXCLUDE_HEALTH_LOGS: skip /health logs (default: false)
    - EXCLUDE_METRICS_LOGS: skip /metrics logs (default: false)
    - EXCLUDE_OPTIONS_LOGS: skip OPTIONS logs (default: true)
    - ALLOWED_LOG_LEVELS: comma-separated list of levels (default: DEBUG,INFO,WARNING,ERROR)
    - MIN_LOG_LEVEL: fallback minimum level threshold if ALLOWED_LOG_LEVELS is empty (default: INFO)
    - REQUEST_LOG_INCLUDE_PATHS: comma-separated path allowlist; if set, only these paths are logged
    - USE_KAFKA_LOGGING: if true, logs go to KafkaHandler (fallback stdout) else stdout
    """

    def __init__(
        self,
        app,
        *,
        logger_name: Optional[str] = None,
        include_4xx: bool = False,
        extra_context_getter: Optional[Callable[[Request, Response], Dict[str, Any]]] = None,
    ):
        super().__init__(app)

        # Filtering configuration
        self.exclude_health_logs = app_env.exclude_health_logs
        self.exclude_metrics_logs = app_env.exclude_metrics_logs
        self.exclude_options_logs = app_env.exclude_options_logs
        self.include_4xx = include_4xx
        include_paths_raw = app_env.request_log_include_paths
        self.include_paths = _parse_csv_paths_env(include_paths_raw)

        # Allowed levels configuration
        allowed_raw = app_env.allowed_log_levels
        self.allowed_log_levels = _parse_allowed_levels_env(allowed_raw)

        # Minimum log level fallback (only used when allowed_log_levels ends up empty)
        min_log_level_str = app_env.min_log_level.upper()
        self.min_log_level = getattr(logging, min_log_level_str, logging.INFO)

        # Logger configuration
        use_kafka = app_env.use_kafka_logging
        # If not provided, use a stable name per service for easier filtering
        if not logger_name:
            svc = app_env.service_name
            logger_name = f"{svc}.request"
        self.logger = get_logger(logger_name, use_kafka=use_kafka)

        self.extra_context_getter = extra_context_getter

    def _should_skip_logging(self, method: str, path: str) -> bool:
        path_lower = _normalize_path_for_match(path)

        # Optional allowlist mode for strict endpoint-only logging
        if self.include_paths and path_lower not in self.include_paths:
            return True

        # Skip CORS preflight logs by default (noise)
        if self.exclude_options_logs and method.upper() == "OPTIONS":
            return True

        # Skip health logs by substring match (consistent across services)
        if self.exclude_health_logs and ("/health" in path_lower or path_lower.endswith("/health")):
            return True

        # Skip metrics logs by substring match
        if self.exclude_metrics_logs and ("/metrics" in path_lower or path_lower.endswith("/metrics")):
            return True

        return False

    def _should_log_by_level(self, status_code: int) -> bool:
        # Map status codes to log levels (consistent with existing services)
        if 200 <= status_code < 300:
            level = logging.INFO
        elif 400 <= status_code < 500:
            level = logging.WARNING
        elif 500 <= status_code < 600:
            level = logging.ERROR
        else:
            level = logging.INFO

        if self.allowed_log_levels:
            return level in self.allowed_log_levels
        return level >= self.min_log_level

    def _get_trace_id(self) -> Optional[str]:
        if not TRACING_AVAILABLE:
            return None
        try:
            current_span = trace.get_current_span()
            if not current_span:
                return None
            span_context = current_span.get_span_context()
            if span_context and span_context.is_valid and span_context.trace_id != 0:
                return format(span_context.trace_id, "032x")
        except Exception:
            return None
        return None

    def _get_org_and_tenant(self, request: Request) -> tuple[Optional[str], Optional[str]]:
        organization = getattr(request.state, "organization", None)
        tenant_id = getattr(request.state, "tenant_id", None)

        # Best-effort contextvar fallbacks (can be missing depending on middleware/task context)
        if not organization:
            try:
                from .context import get_organization as _get_org

                organization = _get_org()
            except Exception:
                pass

        if not tenant_id:
            try:
                from .context import get_tenant_id as _get_tenant

                tenant_id = _get_tenant()
            except Exception:
                pass

        return organization, tenant_id

    def _base_context(self, request: Request, response: Response, *, duration_ms: float) -> Dict[str, Any]:
        method = request.method
        path = request.url.path

        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        correlation_id = get_correlation_id(request)
        organization, tenant_id = self._get_org_and_tenant(request)

        trace_id = self._get_trace_id()
        jaeger_trace_url = trace_id  # OpenSearch uses template to render URL

        ctx: Dict[str, Any] = {
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
        }

        if user_id is not None:
            ctx["user_id"] = user_id
        if api_key_id:
            ctx["api_key_id"] = api_key_id
        if correlation_id:
            ctx["correlation_id"] = correlation_id
        if organization:
            ctx["organization"] = organization
        if tenant_id:
            ctx["tenant_id"] = tenant_id
        if trace_id:
            ctx["trace_id"] = trace_id
        if jaeger_trace_url:
            ctx["jaeger_trace_url"] = jaeger_trace_url

        # Optional per-request details set by routers/service layer
        input_details = getattr(request.state, "input_details", None)
        if input_details:
            ctx["input_details"] = input_details

        output_details = getattr(request.state, "output_details", None)
        if output_details:
            ctx["output_details"] = output_details

        return ctx

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        method = request.method
        path = request.url.path

        try:
            response: Response = await call_next(request)
        except Exception:
            # Let FastAPI exception handlers handle it; we don't log here to avoid duplicates.
            raise

        processing_time_s = time.time() - start_time
        processing_time_ms = processing_time_s * 1000.0
        status_code = response.status_code

        # Always attach process time for downstream visibility
        response.headers["X-Process-Time"] = f"{processing_time_s:.3f}"

        if self._should_skip_logging(method, path):
            return response

        if not self._should_log_by_level(status_code):
            return response

        # Skip 4xx by default (gateway logs these)
        if (400 <= status_code < 500) and not self.include_4xx:
            return response

        log_context = self._base_context(request, response, duration_ms=processing_time_ms)

        # Optional per-service context enrichment
        if self.extra_context_getter:
            try:
                extra_ctx = self.extra_context_getter(request, response) or {}
                if isinstance(extra_ctx, dict):
                    log_context.update(extra_ctx)
            except Exception:
                # Never break request due to logging enrichment
                pass

        if 200 <= status_code < 300:
            self.logger.info(
                f"{method} {path} - {status_code} - {processing_time_s:.3f}s",
                extra={"context": log_context},
            )
        elif 400 <= status_code < 500:
            # Only reached when include_4xx=True
            self.logger.warning(
                f"{method} {path} - {status_code} - {processing_time_s:.3f}s",
                extra={"context": log_context},
            )
        else:
            self.logger.error(
                f"{method} {path} - {status_code} - {processing_time_s:.3f}s",
                extra={"context": log_context},
            )

        return response

