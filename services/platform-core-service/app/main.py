"""
Core Service — FastAPI application factory.

Startup sequence:
  1. PostgreSQL connection (async SQLAlchemy)
  2. Redis connection (async)

Middleware stack: RequestLoggingMiddleware, CORSMiddleware

Authentication is handled at the gateway layer.
"""

import logging
from contextlib import asynccontextmanager

_uvicorn_access = logging.getLogger("uvicorn.access")
_uvicorn_access.handlers.clear()
_uvicorn_access.propagate = False
_uvicorn_access.disabled = True

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import close_database, init_database
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, init_redis
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routes import api_router, versioning

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    # Re-silence uvicorn.access per worker process (uvicorn re-initialises
    # loggers when spawning workers, so the module-level suppression above is
    # not enough when running with --workers > 1).
    _uv = logging.getLogger("uvicorn.access")
    _uv.handlers.clear()
    _uv.propagate = False
    _uv.disabled = True

    logger.info("Starting %s v%s", settings.service_name, settings.service_version)

    # ── Infrastructure startup ──
    await init_database(
        db_url=settings.get_database_url(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        echo=settings.debug,
    )
    await init_redis(
        url=settings.get_redis_url(),
        socket_timeout=settings.redis_timeout,
    )

    # ── Telemetry (optional) ──
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app, excluded_urls="health,ready,docs,redoc,openapi.json"
        )
        logger.info("OpenTelemetry FastAPI instrumentation enabled.")
    except ImportError:
        logger.debug("OpenTelemetry not available — skipping instrumentation.")

    logger.info("Platform-core-service started successfully.")
    yield

    # ── Shutdown ──
    await close_redis()
    await close_database()
    logger.info("Platform-core-service shutdown complete.")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="Platform Core Service",
        version=settings.service_version,
        description=(
            "Platform core service."
        ),
        lifespan=lifespan,
    )

    # ── Exception handlers ──
    register_exception_handlers(app)

    # ── CORS (env-driven) ──
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if not origins:
        origins = ["*"]
    allow_all = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Middleware ──
    app.add_middleware(RequestLoggingMiddleware)

    # ── API versioning headers ──
    versioning.register(app)

    # ── Routes ──
    app.include_router(api_router)

    return app


app = create_app()
