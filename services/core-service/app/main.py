"""
Core Service — FastAPI application factory.

Startup sequence:
  1. PostgreSQL connection (async SQLAlchemy)
  2. Redis connection (async)
  3. ORM table creation (dev-only; production uses Alembic migrations)

Middleware stack (outermost → innermost):
  CORSMiddleware → RequestLoggingMiddleware
"""

import logging
from contextlib import asynccontextmanager

# Silence uvicorn's built-in access logger before FastAPI imports so that
# every request does not produce two log lines.
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

    logger.info(
        "Starting %s v%s [%s]",
        settings.service_name,
        settings.service_version,
        settings.environment,
    )

    is_prod = settings.environment in ("production", "staging")

    # ── Production safety guards ──
    if is_prod and settings.cors_origins == "*":
        raise RuntimeError(
            "FATAL: CORS_ORIGINS='*' is not allowed in production/staging. "
            "Set CORS_ORIGINS to a comma-separated list of allowed origins."
        )
    if is_prod and settings.debug:
        raise RuntimeError("FATAL: DEBUG=true is not allowed in production/staging.")

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

    # ── Optional: auto-create tables in development ──
    # In production, Alembic migrations manage the schema.
    if not is_prod:
        from app.core.database import get_engine
        from app.models import Base  # noqa: F401 — triggers model registration

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables checked/created (development mode).")

    # ── Telemetry (optional) ──
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app, excluded_urls="health,ready,docs,redoc,openapi.json"
        )
        logger.info("OpenTelemetry FastAPI instrumentation enabled.")
    except ImportError:
        logger.debug("OpenTelemetry not available — skipping instrumentation.")

    logger.info("Core-service started successfully.")
    yield

    # ── Shutdown ──
    await close_redis()
    await close_database()
    logger.info("Core-service shutdown complete.")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    is_prod = settings.environment == "production"

    app = FastAPI(
        title="Core Service",
        version=settings.service_version,
        description=(
            "Platform core service — consolidated model & service management. "
            "Replaces the deprecated model-management-service."
        ),
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # ── Exception handlers ──
    register_exception_handlers(app)

    # ── CORS ──
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    allow_all = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware (outermost first) ──
    app.add_middleware(RequestLoggingMiddleware)

    # ── API versioning headers ──
    versioning.register(app)

    # ── Routes ──
    app.include_router(api_router)

    return app


app = create_app()
