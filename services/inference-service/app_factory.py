"""
Main FastAPI application factory for inference service.
Creates and configures the unified inference service with all components.
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from ai4i_core.observability.middleware import ObservabilityMiddleware
from ai4i_core.logging import RequestMiddleware
from routes import router
from config import settings
# from trace.setup import setup_tracing

logger = logging.getLogger(__name__)

_PUBLIC_PATHS = {
    "/", "/health", "/api/v1/inference/health", "/docs", "/redoc", "/openapi.json",
}

# /chat and /chat/completions are load-test stubs (no real model call ever
# happens), so Prometheus tracking is bypassed on this path by default —
# LLM_CHAT_OBSERVABILITY_ENABLED flips it back on for the observability-only
# load-test comparison. Subclassing here (not editing ai4i_core) keeps the
# bypass local to this service.
_CHAT_PATHS = {f"{settings.API_PREFIX}/chat", f"{settings.API_PREFIX}/chat/completions"}

class _ChatAwareObservabilityMiddleware(ObservabilityMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in _CHAT_PATHS and not settings.LLM_CHAT_OBSERVABILITY_ENABLED:
            return await call_next(request)
        return await super().dispatch(request, call_next)
    
# /test is a bare load-test probe (see routes/inference.py) meant to measure
# raw ASGI + routing overhead with none of the service-level middleware in
# the loop — no Prometheus, no request-context/logging, no CORS handling.
# Always bypassed, unconditionally (unlike the chat paths above, there is no
# flag to flip this back on: the whole point of /test is a middleware-free
# baseline). Each middleware below is subclassed locally, not edited in
# ai4i_core, so the bypass stays specific to this one path in this service.
_TEST_PATH = f"{settings.API_PREFIX}/test"
_PUBLIC_PATHS.add(_TEST_PATH)

# @asynccontextmanager
# async def _lifespan(app: FastAPI):
#     """Startup/shutdown lifecycle: flush tracing spans on graceful shutdown."""
#     logger.info("✓ Inference service started")
#     yield
#     from opentelemetry import trace
#     provider = trace.get_tracer_provider()
#     if hasattr(provider, "shutdown"):
#         provider.shutdown()  # flushes the Kafka span exporter
#     from services.base.task_service import close_triton_client
#     await close_triton_client()
#     logger.info("✓ Inference service shutting down")

def _setup_middleware(app: FastAPI) -> None:
    """Configure observability, request-context, and CORS middleware."""
    # Observability — Prometheus /metrics + per-request middleware.
    # Reads OBSERVE_UTIL_* env vars (enabled, debug, metrics_path).
    # setup_observability(app)

    # Request context middleware — seeds trace_id and tenant_id (from the
    # gateway-injected X-Tenant-Id) into contextvars BEFORE handlers run, so
    # inference spans carry attributes.tenantId (read via get_context_attributes).
    app.add_middleware(RequestMiddleware)


def _setup_routes(app: FastAPI) -> None:
    """Register all routes/routers with the application."""
    app.include_router(router, prefix=settings.API_PREFIX)

    # Health check endpoint — excluded from Swagger; used only by Docker HEALTHCHECK
    @app.get("/health", include_in_schema=False)
    async def health_check():
        return {"status": "healthy"}


def _setup_exception_handlers(app: FastAPI) -> None:
    """Configure exception handlers for different error types."""
    from fastapi.responses import JSONResponse
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)}
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        # Full traceback server-side; generic detail to the client.
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}", exc_info=exc
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )


def _setup_openapi_security(app: FastAPI) -> None:
    """Document the gateway-injected auth headers in the OpenAPI schema."""

    def _custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes["bearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        security_schemes["XUserID"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-User-ID",
            "description": "User UUID injected by the gateway. Required for protected endpoints when calling the service directly (bypassing the gateway).",
        }
        security_schemes["XPermissionIDs"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-Permission-IDs",
            "description": "Comma-separated list of permission IDs injected by the gateway after token validation.",
        }
        security_schemes["XBudgetExhausted"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-Budget-Exhausted",
            "description": "Injected by the gateway. Set to 'true' when the tenant's overall budget is exhausted — triggers HTTP 429 (budget_exhausted) for all inference requests.",
        }
        security_schemes["XQuotaExhausted"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-Quota-Exhausted",
            "description": "Injected by the gateway. Comma-separated inference type names whose monthly quota is exhausted (e.g. 'nmt' or 'nmt,asr') — triggers HTTP 429 (quota_exhausted) when the request path matches any exhausted type.",
        }
        for path, methods in (schema.get("paths") or {}).items():
            if path in _PUBLIC_PATHS:
                continue
            for _method, op in (methods or {}).items():
                if isinstance(op, dict):
                    op.setdefault("security", [
                        {"bearerAuth": []},
                        {"XUserID": []},
                        {"XPermissionIDs": []},
                        {"XBudgetExhausted": []},
                        {"XQuotaExhausted": []},
                    ])
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _custom_openapi  # type: ignore[assignment]


def create_inference_app() -> FastAPI:
    """
    Entry point for creating the inference service application.
    Constructs a fully configured app with all components wired.

    Returns:
        Configured FastAPI application ready to serve inference requests
    """
    # Initialize tracing FIRST so the tracer provider exists before any spans
    # setup_tracing()

    app = FastAPI(
        title="AI4I Inference Service",
        description="Unified inference endpoint for NMT, ASR, OCR, NER, LLM and other task services",
        version="1.0.0",
        # API docs are opt-out: keep enabled for dev, disable in production
        # via ENABLE_DOCS=false (OWASP API8 — security misconfiguration).
        docs_url="/docs" if settings.ENABLE_DOCS else None,
        redoc_url="/redoc" if settings.ENABLE_DOCS else None,
        openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
        # lifespan=_lifespan,
    )

    _setup_openapi_security(app)
    _setup_middleware(app)
    _setup_routes(app)
    _setup_exception_handlers(app)

    logger.info("✓ Inference service application created and configured")
    return app
