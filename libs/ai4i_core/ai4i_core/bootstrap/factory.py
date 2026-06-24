"""
Service app factory — the single way to create a FastAPI app in AI4I-Core.

Middleware execution order (LIFO — last added runs first on request):

  CORSMiddleware               ← outermost: applies CORS headers before anything else
  RequestMiddleware            ← seeds trace_id, logs the request
  OTel / FastAPIInstrumentor   ← CorrelationPropagator reads trace_id here

CORSMiddleware MUST be added last so it is outermost and CORS headers are
applied even when inner middleware short-circuits the request.
RequestMiddleware is added before CORSMiddleware so it still runs before OTel.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    service_name: str
    version: str = "1.0.0"
    description: str = ""
    environment: str = "development"

    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    hide_docs_in_production: bool = True

    telemetry_enabled: bool = True
    jaeger_endpoint: Optional[str] = None

    log_level: str = "INFO"

    telemetry_exclude_paths: set[str] = field(default_factory=lambda: {
        "/health", "/ready", "/docs", "/redoc", "/openapi.json",
    })


def create_service_app(config: Optional[ServiceConfig] = None, **kwargs) -> FastAPI:
    """Create a fully bootstrapped FastAPI application."""
    if config is None:
        config = ServiceConfig(**kwargs)

    is_prod = config.environment in ("production", "staging")

    app = FastAPI(
        title=config.service_name,
        version=config.version,
        description=config.description or f"{config.service_name} microservice",
        docs_url=None if (is_prod and config.hide_docs_in_production) else "/docs",
        redoc_url=None if (is_prod and config.hide_docs_in_production) else "/redoc",
        openapi_url=None if (is_prod and config.hide_docs_in_production) else "/openapi.json",
    )

    # ── 1. Exception handlers ──
    try:
        from ai4i_core.exceptions import register_exception_handlers
        register_exception_handlers(app)
    except ImportError:
        pass

    # ── 2. Configure logging ──
    from ai4i_core.logging import configure_logging
    configure_logging(service_name=config.service_name, log_level=config.log_level)

    # ── 3. OTel instrumentation ──
    if config.telemetry_enabled:
        try:
            from ai4i_core.telemetry import setup_tracing
            setup_tracing(config.service_name, config.jaeger_endpoint)
        except ImportError:
            pass

        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls=",".join(config.telemetry_exclude_paths),
            )
        except ImportError:
            pass

    # ── 4. Request middleware (seeds trace_id before OTel propagator runs) ──
    from ai4i_core.logging import RequestMiddleware
    app.add_middleware(RequestMiddleware)

    # ── 5. CORS (outermost — added last, runs first) ──
    allow_all = config.cors_origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 6. Health endpoints ──
    @app.get("/")
    async def _root():
        return {"service": config.service_name, "version": config.version, "status": "running"}

    @app.get("/health")
    async def _health():
        return {"status": "healthy"}

    app.state.service_config = config
    logger.info("[bootstrap] %s v%s ready [%s]", config.service_name, config.version, config.environment)
    return app
