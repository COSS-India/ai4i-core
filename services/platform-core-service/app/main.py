"""
Platform Core Service — FastAPI application factory.
No tracing or observability — logging only.
"""

import logging
from contextlib import asynccontextmanager
import time

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from starlette.requests import Request
from app.core.config import settings
from app.core.database import close_database, init_database
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, init_redis
from app.routes import api_router, versioning
from app.services.pay_per_use.pay_per_use_service import warm_pricing_cache
from app.services.service_service import EndpointValidationFailedError

from ai4icore_core.logging import configure_logging, RequestMiddleware
from ai4icore_core.exceptions import ErrorDetail

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
    await warm_pricing_cache()

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

    @app.exception_handler(EndpointValidationFailedError)
    async def endpoint_validation_error_handler(
        _request: Request, exc: EndpointValidationFailedError
    ) -> JSONResponse:
        body = {
            "detail": ErrorDetail(
                message=exc.message,
                code=exc.code,
                timestamp=time.time(),
                details="; ".join(exc.errors),
            ).dict()
        }
        return JSONResponse(status_code=exc.status_code, content=body)

    # CORS is handled at the nginx gateway.
    app.add_middleware(RequestMiddleware)

    versioning.register(app)
    app.include_router(api_router)
    app.mount("/metrics", make_asgi_app())

    # OpenAPI security: Bearer JWT lock on all endpoints except health/root.
    _PUBLIC_PATHS = {"/", "/health", "/ready", "/docs", "/redoc", "/openapi.json"}

    def _custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {})["bearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        for path, methods in (schema.get("paths") or {}).items():
            if path in _PUBLIC_PATHS:
                continue
            for _method, op in (methods or {}).items():
                if isinstance(op, dict):
                    op.setdefault("security", [{"bearerAuth": []}])
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _custom_openapi  # type: ignore[assignment]

    return app


app = create_app()