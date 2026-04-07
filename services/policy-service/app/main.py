from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.pii_types import router as pii_types_router
from app.api.routes.policies import router as policies_router
from app.api.routes.audit_logs import router as audit_logs_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import AppDBBase as Base
from app.db.session import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    if engine is not None:
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

    # Base URL: /v1
    PREFIX = "/v1"
    application.include_router(health_router)
    application.include_router(pii_types_router, prefix=PREFIX)
    application.include_router(policies_router, prefix=PREFIX)
    # tenant assignment is handled via policy create/update; no separate tenant router
    application.include_router(audit_logs_router, prefix=PREFIX)

    return application


def get_app() -> FastAPI:
    return create_app()
