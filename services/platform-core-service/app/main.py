"""
Platform Core Service — FastAPI application factory.
No tracing or observability — logging only.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
import time

import httpx
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.requests import Request
from app.core.config import settings
from app.core.database import (
    close_auth_database,
    close_database,
    init_auth_database,
    init_database,
)
from app.core.exceptions import register_exception_handlers
from app.core.database import get_primary_session_factory as _get_pii_session_factory
from app.core.redis import close_redis, get_redis_client, init_redis
from app.routes import api_router, versioning
from app.services.pay_per_use.pay_per_use_service import warm_pricing_cache

# services/model-management/ is hyphenated; importlib is the only way to pull symbols out.
import importlib as _importlib
EndpointValidationFailedError = _importlib.import_module(
    "app.services.model-management.service_service"
).EndpointValidationFailedError

from ai4icore_core.logging import configure_logging, RequestMiddleware
from ai4icore_core.exceptions import ErrorDetail

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.service_name, settings.service_version)

    # Shared HTTP client — connection pool reused across all Prometheus queries.
    app.state.http_client = httpx.AsyncClient()

    # ── Core DB & Redis ───────────────────────────────────────────────────
    await init_database(
        db_url=settings.get_database_url(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        echo=settings.debug,
    )
    # Secondary auth_db engine — no-op if AUTH_DB_NAME is not configured.
    init_auth_database()
    await init_redis(
        url=settings.get_redis_url(),
        socket_timeout=settings.redis_timeout,
    )
    await warm_pricing_cache()

    # ── Telemetry / OpenSearch ────────────────────────────────────────────
    if settings.opensearch_url and settings.opensearch_username and settings.opensearch_password:
        from app.utils.opensearch_client import OpenSearchTraceClient

        opensearch_client = OpenSearchTraceClient(
            url=settings.opensearch_url,
            username=settings.opensearch_username,
            password=settings.opensearch_password,
            index=settings.opensearch_index,
        )
        if opensearch_client.connect():
            app.state.opensearch_client = opensearch_client
            logger.info("OpenSearch client connected for telemetry")
        else:
            logger.warning("Could not connect to OpenSearch — telemetry will return empty results")
    else:
        logger.info("OpenSearch not configured (OPENSEARCH_URL, OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD required)")

    # Alert config sync background loop — only when explicitly enabled, so the
    # service can run without alerting wired up (and to avoid double-writes
    # during the side-by-side rollout window).
    app.state.alert_sync_task = None
    if settings.alert_sync_enabled:
        from app.dependencies.services import get_sync_service

        sync_service = get_sync_service()
        app.state.alert_sync_task = asyncio.create_task(sync_service.run_periodic_loop())
        logger.info("Alert config sync loop started (interval=%ss)", settings.sync_interval)
    else:
        logger.info("Alert config sync disabled (ALERT_SYNC_ENABLED=false)")

    # ── PII singletons ────────────────────────────────────────────────────
    # Import via importlib because the services directory uses a hyphenated name.
    _pii_svc = _importlib.import_module("app.services.pii-management")
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
    async with _get_pii_session_factory()() as db:
        await kb_svc.refresh(db)
        await policy_sync.refresh(db)

    # Start Redis pub/sub listener (background task — auto-cancelled on shutdown).
    async def _pii_db_factory():
        async with _get_pii_session_factory()() as session:
            yield session

    policy_sync.start_listener(
        redis_client=app.state.redis_client,
        db_factory=_pii_db_factory,
    )

    logger.info("PII guard ready (kb=%s, policy_sync=%s)", kb_svc.ready, policy_sync.ready)

    yield

    sync_task = getattr(app.state, "alert_sync_task", None)
    if sync_task is not None:
        sync_task.cancel()
        await asyncio.gather(sync_task, return_exceptions=True)

    # ── Shutdown ──────────────────────────────────────────────────────────
    await app.state.http_client.aclose()
    await policy_sync.stop_listener()
    await close_redis()
    await close_auth_database()
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
        for path, methods in (schema.get("paths") or {}).items():
            if path in _PUBLIC_PATHS:
                continue
            for _method, op in (methods or {}).items():
                if isinstance(op, dict):
                    op.setdefault("security", [{"bearerAuth": []}, {"XUserID": []}, {"XPermissionIDs": []}])
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _custom_openapi  # type: ignore[assignment]

    return app


app = create_app()
