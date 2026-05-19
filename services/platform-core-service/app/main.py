"""
Platform Core Service — FastAPI application factory.
No tracing or observability — logging only.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import close_database, init_database
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, init_redis
from app.routes import api_router, versioning

from ai4icore_core.logging import configure_logging, RequestMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.service_name, settings.service_version)

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

    yield

    await close_redis()
    await close_database()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Platform Core Service",
        version=settings.service_version,
        description="Platform core service.",
        lifespan=lifespan,
    )

    configure_logging(service_name=settings.service_name)
    register_exception_handlers(app)

    # CORS is handled at the nginx gateway.
    app.add_middleware(RequestMiddleware)

    versioning.register(app)
    app.include_router(api_router)

    return app


app = create_app()
