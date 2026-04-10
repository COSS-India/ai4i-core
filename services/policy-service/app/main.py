from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api.routes.health import router as health_router
from app.api.routes.pii_types import router as pii_types_router
from app.api.routes.policies import router as policies_router
from app.api.routes.audit_logs import router as audit_logs_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import AppDBBase as Base
from app.db.session import get_engine
import logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = get_engine()
    if engine is not None and settings.auto_create_tables:
        logging.getLogger(__name__).warning(
            "AUTO_CREATE_TABLES is enabled; creating tables from ORM metadata at startup. "
            "Disable this in environments managed by Alembic migrations."
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level)

    application = FastAPI(
        title="Policy Service — PII Policy Module",
        description="Manage PII detection types, sanitisation policies, tenant assignments, and audit trail.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    def custom_openapi():
        if application.openapi_schema:
            return application.openapi_schema

        schema = get_openapi(
            title=application.title,
            version=application.version,
            description=application.description,
            routes=application.routes,
        )

        # Add Bearer auth scheme so Swagger UI shows "Authorize" and sends Authorization header.
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes["bearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }

        # Apply security to all endpoints except /health (healthcheck must remain unauthenticated).
        for path, methods in (schema.get("paths") or {}).items():
            if path == "/health":
                continue
            for _method, op in (methods or {}).items():
                if isinstance(op, dict):
                    op.setdefault("security", [{"bearerAuth": []}])

        application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = custom_openapi  # type: ignore[assignment]

    # Base URL: follow platform convention (/api/v1/<service>)
    PREFIX = "/api/v1/policy-service"
    # Keep /health for backward compatibility with local/docker healthchecks.
    application.include_router(health_router)
    application.include_router(health_router, prefix=PREFIX)
    application.include_router(pii_types_router, prefix=PREFIX)
    application.include_router(policies_router, prefix=PREFIX)
    # tenant assignment is handled via policy create/update; no separate tenant router
    application.include_router(audit_logs_router, prefix=PREFIX)

    return application


def get_app() -> FastAPI:
    return create_app()
