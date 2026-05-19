"""
Auth Service — FastAPI application factory.

Auth-service is the only service that performs JWT verification.
It issues tokens and verifies them for the /auth/validate endpoint.
"""

import asyncio
import json
import logging
import pathlib
from contextlib import asynccontextmanager
from typing import Any

# Disable uvicorn's built-in access logger at module load time.
# RequestLoggingMiddleware handles request logging — without this,
# every request produces two log lines (custom format + uvicorn format).
_uvicorn_access = logging.getLogger("uvicorn.access")
_uvicorn_access.handlers.clear()
_uvicorn_access.propagate = False
_uvicorn_access.disabled = True
_uvicorn_access.setLevel(logging.CRITICAL + 1)

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.permission_checker import PermissionChecker, set_global_endpoint_permission_map

from app.core.config import settings
from app.core.constants import ENV_DEVELOPMENT
from app.core.database import close_database, init_database
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, init_redis
from app.core.security import key_manager
from app.dependencies.auth import init_jwt_verifier
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routes import api_router, versioning
from app.services.role_permission_cache import role_permission_cache

# Optional dep — guarded so the module still imports without opentelemetry installed.
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
except ImportError:
    FastAPIInstrumentor = None


logger = logging.getLogger(__name__)

# Raw api_permissions.json payload — loaded once at startup (see load_api_permissions).
API_PERMISSIONS: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Re-disable uvicorn.access in each worker process.
    # Uvicorn re-initialises loggers per worker, so the module-level
    # suppression above is not enough when running with --workers > 1.
    _uv = logging.getLogger("uvicorn.access")
    _uv.handlers.clear()
    _uv.propagate = False
    _uv.disabled = True
    _uv.setLevel(logging.CRITICAL + 1)

    logger.info("Starting %s v%s [%s]", settings.service_name, settings.service_version, settings.environment)

    # Production safety: DEBUG=true only allowed in local dev.
    if settings.environment != ENV_DEVELOPMENT and settings.debug:
        raise RuntimeError(f"FATAL: DEBUG=true is not allowed in {settings.environment}.")

    # Startup
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
    await key_manager.initialize()
    await init_jwt_verifier()

    # Load API-to-permission mapping (in-memory; legacy Redis key removed).
    # Stored on app.state — read by validation.py via request.app.state.
    await _load_api_permissions_with_retry(app)

    # In-memory role -> permission cache with 60s refresh
    await role_permission_cache.start()

    # Telemetry (optional — package may not be installed)
    if FastAPIInstrumentor is not None:
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,docs,redoc,openapi.json,auth/validate")
        logger.info("OpenTelemetry FastAPI instrumentation enabled.")
    else:
        logger.info("Telemetry not available, skipping.")

    yield

    # Shutdown
    await role_permission_cache.stop()
    await close_redis()
    await close_database()
    logger.info("Shutdown complete.")


async def load_api_permissions(app: FastAPI) -> None:
    """
    Load api_permissions.json into API_PERMISSIONS and build the
    endpoint -> permission_id map used by PermissionChecker, then
    publish it on app.state for routes to read via request.app.state.

    permissionRequired is the integer DB id of the permission, baked into
    the JSON. The IDs are owned by the seeder
    (infrastructure/databases/seeders/postgres/auth_roles_permissions_seeder.py).
    Endpoints absent from this list are public.
    """
    json_path = pathlib.Path(__file__).parent.parent / "api_permissions.json"
    if not json_path.exists():
        logger.info("No api_permissions.json found, skipping.")
        app.state.permission_checker = None
        return

    try:
        payload = json.loads(json_path.read_text())
        API_PERMISSIONS.clear()
        API_PERMISSIONS.update(payload)

        endpoint_to_id: dict[str, int] = {
            m["endpoint"]: int(m["permissionRequired"])
            for m in API_PERMISSIONS.get("apiMappings", [])
        }

        checker = PermissionChecker()
        checker._api_permission_map = endpoint_to_id
        set_global_endpoint_permission_map(endpoint_to_id)
        app.state.permission_checker = checker

        logger.info("API permission mapping loaded: %d endpoints.", len(endpoint_to_id))
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Failed to load API permission mapping: %s", exc)
        app.state.permission_checker = None
        return
    except OSError as exc:
        logger.warning("Failed to load API permission mapping: %s", exc)
        raise


async def _load_api_permissions_with_retry(
    app: FastAPI,
    max_attempts: int = 8,
    base_delay_seconds: float = 1.0,
) -> None:
    """Retry api permission mapping load on infra readiness failures."""
    last_exc: OSError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            await load_api_permissions(app)
            return
        except OSError as exc:
            last_exc = exc
            logger.warning(
                "API permission mapping load retry %d/%d after connection failure: %s",
                attempt,
                max_attempts,
                exc,
            )
            await asyncio.sleep(base_delay_seconds * attempt)

    if last_exc:
        logger.error("Giving up loading API permission mapping after %d attempts: %s", max_attempts, last_exc)
        app.state.permission_checker = None


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

    # Exception handlers
    register_exception_handlers(app)

    # Middleware (order matters — outermost first)
    # CORS is handled at the nginx gateway, not here.
    app.add_middleware(RequestLoggingMiddleware)

    # API versioning — shared middleware for version headers + deprecation
    versioning.register(app)

    # Routes
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
        components.setdefault("securitySchemes", {})["bearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        for path, methods in (schema.get("paths") or {}).items():
            if path in _PUBLIC_PATHS:
                continue
            for _method, op in (methods or {}).items():
                if isinstance(op, dict) and _PUBLIC_TAG not in (op.get("tags") or []):
                    op.setdefault("security", [{"bearerAuth": []}])
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _custom_openapi  # type: ignore[assignment]

    return app


app = create_app()
