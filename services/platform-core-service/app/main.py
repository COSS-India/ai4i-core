"""
Platform Core Service — FastAPI application factory.
No tracing or observability — logging only.
"""

import importlib
import logging
from contextlib import asynccontextmanager
import time

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.requests import Request
from app.core.config import settings
from app.core.database import close_database, init_database
from app.core.exceptions import register_exception_handlers
from app.core.pii_database import close_pii_database, init_pii_database, _pii_session_factory
from app.core.redis import close_redis, get_redis_client, init_redis
from app.routes import api_router, versioning
from app.services.service_service import EndpointValidationFailedError

from ai4icore_core.logging import configure_logging, RequestMiddleware
from ai4icore_core.exceptions import ErrorDetail

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.service_name, settings.service_version)

    # ── Core DB & Redis ───────────────────────────────────────────────────
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

    # ── PII DB ────────────────────────────────────────────────────────────
    await init_pii_database(
        db_url=settings.get_pii_database_url(),
        pool_size=settings.pii_db_pool_size,
        max_overflow=settings.pii_db_max_overflow,
        echo=settings.debug,
    )

    # ── PII singletons ────────────────────────────────────────────────────
    # Import via importlib because the services directory uses a hyphenated name.
    _pii_svc = importlib.import_module("app.services.pii-management")
    kb_svc        = _pii_svc.KnowledgeBaseService()
    policy_sync   = _pii_svc.PolicySyncService()
    audit_svc     = _pii_svc.AuditService()
    detection_eng = _pii_svc.DetectionEngine(kb=kb_svc, ner_service_url=settings.ner_service_url)
    redaction_svc = _pii_svc.RedactionService(
        policy_sync=policy_sync,
        detection_engine=detection_eng,
        audit_service=audit_svc,
    )

    # Expose on app.state so routes can access them without DI re-instantiation.
    app.state.pii_kb            = kb_svc
    app.state.pii_policy_sync   = policy_sync
    app.state.pii_redaction_service = redaction_svc

    # Also expose redis client for policy pub/sub broadcast in admin routes.
    app.state.redis_client = get_redis_client()

    # Initial load from DB.
    async with _pii_session_factory() as db:
        await kb_svc.refresh(db)
        await policy_sync.refresh(db)

    # Start Redis pub/sub listener (background task — auto-cancelled on shutdown).
    async def _pii_db_factory():
        async with _pii_session_factory() as session:
            yield session

    await policy_sync.start_listener(
        redis_client=app.state.redis_client,
        db_factory=_pii_db_factory,
    )

    logger.info("PII guard ready (kb=%s, policy_sync=%s)", kb_svc.ready, policy_sync.ready)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    await policy_sync.stop_listener()
    await close_redis()
    await close_pii_database()
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