"""
Service app factory — the single way to create a FastAPI app in AI4I-Core.

Wires up everything that every service needs:
1. Standardized exception handlers (from ai4icore_constants)
2. Structured JSON logging (from ai4icore_logging)
3. Auth middleware with JWT verification (from ai4icore_auth)
4. CORS configuration (production-safe)
5. Request logging middleware
6. Health endpoint
7. Telemetry (optional)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Configuration for service bootstrap."""

    service_name: str
    version: str = "1.0.0"
    description: str = ""
    environment: str = "development"

    # Auth
    jwks_url: Optional[str] = None
    jwt_issuer: str = "auth-service"
    jwt_audience: Optional[str] = None
    require_auth: bool = False  # False = context extraction only, True = block unauthenticated

    # CORS
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    # Docs
    hide_docs_in_production: bool = True

    # Telemetry
    telemetry_enabled: bool = True
    jaeger_endpoint: Optional[str] = None

    # Logging
    log_level: str = "INFO"

    # Skip auth paths
    auth_skip_paths: set[str] = field(default_factory=lambda: {
        "/", "/health", "/ready", "/docs", "/redoc", "/openapi.json",
    })


def create_service_app(
    config: Optional[ServiceConfig] = None,
    **kwargs,
) -> FastAPI:
    """
    Create a fully bootstrapped FastAPI application.

    This is the STANDARD way to create a service in AI4I-Core.
    Every service gets identical: exception handling, logging, auth, CORS.

    Args:
        config: ServiceConfig object, or pass kwargs directly.

    Returns:
        Configured FastAPI app ready for route registration.
    """
    if config is None:
        config = ServiceConfig(**kwargs)

    is_prod = config.environment in ("production", "staging")

    # ── Create app ──
    app = FastAPI(
        title=config.service_name,
        version=config.version,
        description=config.description or f"{config.service_name} microservice",
        docs_url=None if (is_prod and config.hide_docs_in_production) else "/docs",
        redoc_url=None if (is_prod and config.hide_docs_in_production) else "/redoc",
        openapi_url=None if (is_prod and config.hide_docs_in_production) else "/openapi.json",
    )

    # ── 1. Exception handlers (from ai4icore_exceptions) ──
    try:
        from ai4icore_exceptions import register_exception_handlers
        register_exception_handlers(app)
        logger.info("[bootstrap] Exception handlers registered.")
    except ImportError:
        logger.warning("[bootstrap] ai4icore_exceptions not available, using default exception handling.")

    # ── 2. CORS ──
    allow_all = config.cors_origins == ["*"]
    if is_prod and allow_all:
        logger.warning("[bootstrap] CORS_ORIGINS='*' in production — restrict to specific origins.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 3. Logging middleware (from ai4icore_logging) ──
    try:
        from ai4icore_logging import (
            configure_logging,
            CorrelationMiddleware,
            RequestLoggingMiddleware,
        )
        configure_logging(
            service_name=config.service_name,
            log_level=config.log_level,
        )
        app.add_middleware(RequestLoggingMiddleware)
        app.add_middleware(CorrelationMiddleware)
        logger.info("[bootstrap] Structured logging configured via ai4icore_logging.")
    except ImportError:
        logger.warning("[bootstrap] ai4icore_logging not available, using basic logging.")
        logging.basicConfig(level=getattr(logging, config.log_level, logging.INFO))

    # ── 4. Auth middleware (from ai4icore_auth) ──
    if config.jwks_url:
        try:
            from ai4icore_auth import AuthMiddleware, JWTVerifier

            verifier = JWTVerifier(
                jwks_url=config.jwks_url,
                issuer=config.jwt_issuer,
                audience=config.jwt_audience,
            )

            app.add_middleware(
                AuthMiddleware,
                jwt_verifier_factory=lambda: verifier,
                service_name=config.service_name,
                skip_paths=config.auth_skip_paths,
                require_auth=config.require_auth,
            )

            # Initialize verifier on startup
            @app.on_event("startup")
            async def _init_verifier():
                await verifier.initialize()
                logger.info("[bootstrap] JWTVerifier initialized with JWKS from %s", config.jwks_url)

            logger.info("[bootstrap] Auth middleware registered (JWKS: %s).", config.jwks_url)
        except ImportError:
            logger.warning("[bootstrap] ai4icore_auth not available, auth middleware skipped.")

    # ── 5. Telemetry (optional) ──
    if config.telemetry_enabled:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls=",".join(config.auth_skip_paths - {"/"}),
            )
            logger.info("[bootstrap] OpenTelemetry FastAPI instrumentation enabled.")
        except ImportError:
            pass

    # ── 6. Health endpoint ──
    @app.get("/")
    async def _root():
        return {"service": config.service_name, "version": config.version, "status": "running"}

    @app.get("/health")
    async def _health():
        return {"status": "healthy"}

    # Store config on app for downstream access
    app.state.service_config = config

    logger.info(
        "[bootstrap] %s v%s ready [%s]",
        config.service_name, config.version, config.environment,
    )

    return app
