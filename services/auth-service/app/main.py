"""
Auth Service — FastAPI application factory.

Auth-service is the FIRST CONSUMER of ai4icore_auth shared library.
It creates tokens (service-specific), but verifies them through the
same shared JWTVerifier that every other microservice uses.
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
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from ai4icore_core.auth.middleware import AuthMiddleware
from ai4icore_core.auth.permission_checker import PermissionChecker, set_global_endpoint_permission_map

from app.core.config import settings
from app.core.database import close_database, get_db, init_database
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, get_redis_client, init_redis
from app.core.security import key_manager
from app.dependencies.auth import get_jwt_verifier, init_jwt_verifier
from app.middleware.request_logging import RequestLoggingMiddleware
from app.models.role import Permission
from app.routes import api_router
from app.services.cache_service import CacheService


logger = logging.getLogger(__name__)

# Raw api_permissions.json payload — loaded once at startup (see load_api_permissions).
API_PERMISSIONS: dict[str, Any] = {}

# Module-level permission checker — set during startup, used by endpoint guard
_permission_checker: PermissionChecker | None = None


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

    # Production safety checks
    is_prod = settings.environment in ("production", "staging")
    if is_prod and settings.cors_origins == "*":
        raise RuntimeError(
            "FATAL: CORS_ORIGINS='*' is not allowed in production/staging. "
            "Set CORS_ORIGINS to specific origins (comma-separated)."
        )
    if is_prod and settings.debug:
        raise RuntimeError("FATAL: DEBUG=true is not allowed in production/staging.")

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

    # Load API-to-permission mapping (in-memory; legacy Redis key removed)
    await _load_api_permissions_with_retry()

    # Telemetry (optional)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,docs,redoc,openapi.json")
        logger.info("OpenTelemetry FastAPI instrumentation enabled.")
    except ImportError:
        logger.info("Telemetry not available, skipping.")

    yield

    # Shutdown
    await close_redis()
    await close_database()
    logger.info("Shutdown complete.")


def get_permission_checker() -> PermissionChecker | None:
    return _permission_checker


async def load_api_permissions() -> None:
    """
    Load api_permissions.json into API_PERMISSIONS and resolve endpoint → permission_id
    into memory (PermissionChecker + process-wide map for shared library consumers).
    """
    global _permission_checker

    json_path = pathlib.Path(__file__).parent.parent / "api_permissions.json"
    if not json_path.exists():
        logger.info("No api_permissions.json found, skipping.")
        return

    try:
        payload = json.loads(json_path.read_text())
        API_PERMISSIONS.clear()
        API_PERMISSIONS.update(payload)

        redis_client = get_redis_client()
        cache_service = CacheService(redis_client)
        await cache_service.delete_legacy_api_perms_key()

        name_to_id: dict[str, int] = {}
        async for db in get_db():
            result = await db.execute(select(Permission.name, Permission.id))
            for name, pid in result.all():
                key = name.value if hasattr(name, "value") else str(name)
                name_to_id[key] = pid
            break

        endpoint_to_id: dict[str, str] = {}
        for m in API_PERMISSIONS.get("apiMappings", []):
            perm_name = m.get("permissionRequired")
            if perm_name is None:
                continue
            perm_id = name_to_id.get(perm_name)
            if perm_id is not None:
                endpoint_to_id[m["endpoint"]] = str(perm_id)
            else:
                logger.warning("Permission '%s' not found in DB, skipping.", perm_name)

        checker = PermissionChecker()
        checker._api_permission_map = endpoint_to_id
        set_global_endpoint_permission_map(endpoint_to_id)
        _permission_checker = checker

        logger.info("API permission mapping loaded: %d endpoints → DB IDs.", len(endpoint_to_id))
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Failed to load API permission mapping: %s", exc)
        return
    except OSError as exc:
        logger.warning("Failed to load API permission mapping: %s", exc)
        raise


async def _load_api_permissions_with_retry(
    max_attempts: int = 8,
    base_delay_seconds: float = 1.0,
) -> None:
    """Retry api permission mapping load on infra readiness failures."""
    last_exc: OSError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            await load_api_permissions()
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


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    is_prod = settings.environment == "production"

    app = FastAPI(
        title="Auth Service",
        version=settings.service_version,
        description="Authentication & Authorization microservice",
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # Exception handlers
    register_exception_handlers(app)

    # CORS — restricted in production, open in dev
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    allow_all = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware (order matters — outermost first)
    app.add_middleware(RequestLoggingMiddleware)
    # Shared AuthMiddleware with lazy verifier factory —
    # verifier is initialized in lifespan (after key_manager),
    # factory resolves it on first request.
    app.add_middleware(
        AuthMiddleware,
        jwt_verifier_factory=get_jwt_verifier,
        require_auth=False,  # Context extraction only — route deps enforce auth
    )

    # API versioning — shared middleware for version headers + deprecation
    from app.routes import versioning
    versioning.register(app)

    # Routes
    app.include_router(api_router)

    return app


app = create_app()
