"""
Auth Service — FastAPI application factory.

Auth-service is the only service that performs JWT verification.
It issues tokens and verifies them for the /auth/validate endpoint.
No tracing or observability — logging only.
"""

import asyncio
import json
import logging
import pathlib
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.permission_checker import set_global_endpoint_permission_map
from app.core import pii_crypto
from app.core.config import settings
from app.core.constants import ENV_DEVELOPMENT
from ai4i_core.ppu import configure_catalogue, get_catalogue
from app.core.database import (
    close_database,
    close_platform_core_database,
    get_platform_core_session_factory,
    init_database,
    init_platform_core_database,
)
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, get_redis_client, init_redis
from app.core.security import key_manager
from app.dependencies.auth import init_jwt_verifier
from app.routes import api_router, versioning
from app.services.role_permission_cache import role_permission_cache
from app.services.tenant_name_cache import tenant_name_cache

from ai4i_core.logging import configure_logging, RequestMiddleware

logger = logging.getLogger(__name__)

API_PERMISSIONS: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s [%s]", settings.service_name, settings.service_version, settings.environment)

    if settings.environment != ENV_DEVELOPMENT and settings.debug:
        raise RuntimeError(f"FATAL: DEBUG=true is not allowed in {settings.environment}.")

    # Fail fast on a missing/malformed PII encryption key: every email/phone
    # bind needs it, so a bad config must crash at boot, not on the first login.
    pii_crypto.validate_key()

    await init_database(
        db_url=settings.get_database_url(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        echo=settings.debug,
    )
    await init_redis(
        url=settings.get_redis_url(),
        socket_timeout=settings.redis_timeout,
        redis_db=settings.redis_db,
    )
    init_platform_core_database()

    # The inference-type catalogue backs per-service quota enforcement in
    # /auth/validate. Redis first (platform-core writes core:inference_type:*
    # there — both services must share a host AND logical DB, both default to
    # REDIS_DB=0), then the platform-core database when it is configured.
    #
    # Warming here is best-effort on purpose: an unreachable catalogue must not
    # stop auth-service booting. It degrades to skipping per-service quota
    # checks, never to a spurious 429.
    configure_catalogue(
        redis_factory=get_redis_client,
        session_factory=get_platform_core_session_factory(),
    )
    try:
        types = await get_catalogue().refresh()
        logger.info("Inference type catalogue warmed: %d types.", len(types))
    except Exception as exc:
        logger.warning("Inference type catalogue warm-up skipped: %s", exc)
    key_manager.initialize()
    init_jwt_verifier()
    await _load_api_permissions_with_retry(app)
    await role_permission_cache.start()
    await tenant_name_cache.start()

    yield

    await tenant_name_cache.stop()
    await role_permission_cache.stop()
    await close_redis()
    await close_database()
    await close_platform_core_database()
    logger.info("Shutdown complete.")


def load_api_permissions(app: FastAPI) -> None:
    """Populate the process-wide endpoint→permission map.

    The single source of truth is the module-level map in
    app.core.permission_checker (consumed via its `permission_checker`
    singleton) — nothing is stashed on app.state. When loading fails, the map
    stays empty and consumers fail closed via endpoint_permission_map_loaded().
    """
    json_path = pathlib.Path(__file__).parent.parent / "api_permissions.json"
    if not json_path.exists():
        logger.info("No api_permissions.json found, skipping.")
        return

    try:
        payload = json.loads(json_path.read_text())
        API_PERMISSIONS.clear()
        API_PERMISSIONS.update(payload)

        endpoint_to_id: dict[str, int] = {
            m["endpoint"]: int(m["permissionRequired"])
            for m in API_PERMISSIONS.get("apiMappings", [])
        }

        set_global_endpoint_permission_map(endpoint_to_id)

        logger.info("API permission mapping loaded: %d endpoints.", len(endpoint_to_id))
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Failed to load API permission mapping: %s", exc)
    except OSError as exc:
        logger.warning("Failed to load API permission mapping: %s", exc)
        raise


async def _load_api_permissions_with_retry(
    app: FastAPI,
    max_attempts: int = 8,
    base_delay_seconds: float = 1.0,
) -> None:
    last_exc: OSError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            load_api_permissions(app)
            return
        except OSError as exc:
            last_exc = exc
            logger.warning(
                "API permission mapping load retry %d/%d: %s",
                attempt, max_attempts, exc,
            )
            await asyncio.sleep(base_delay_seconds * attempt)

    if last_exc:
        logger.error("Giving up loading API permission mapping after %d attempts: %s", max_attempts, last_exc)


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    hide_docs = False
    app = FastAPI(
        title="Auth Service",
        version=settings.service_version,
        description="Authentication & Authorization microservice",
        lifespan=lifespan,
        docs_url=None if hide_docs else "/docs",
        redoc_url=None if hide_docs else "/redoc",
        openapi_url=None if hide_docs else "/openapi.json",
    )

    configure_logging(service_name=settings.service_name)
    register_exception_handlers(app)

    # CORS is handled at the nginx gateway.
    app.add_middleware(RequestMiddleware)

    versioning.register(app)
    app.include_router(api_router)

    # OpenAPI security: Bearer JWT lock on all endpoints except public auth routes.
    # Routes tagged "Authentication" (auth.py: login, register, etc.) stay unlocked.
    _PUBLIC_PATHS = {"/", "/health", "/ready", "/docs", "/redoc", "/openapi.json"}
    _PUBLIC_TAG = "Authentication"

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
                if isinstance(op, dict) and _PUBLIC_TAG not in (op.get("tags") or []):
                    op.setdefault("security", [{"bearerAuth": []}, {"XUserID": []}, {"XPermissionIDs": []}])
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _custom_openapi  # type: ignore[assignment]

    return app


app = create_app()
