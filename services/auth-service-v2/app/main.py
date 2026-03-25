"""
Auth Service v2 — FastAPI application factory.

Auth-service is the FIRST CONSUMER of ai4icore_auth shared library.
It creates tokens (service-specific), but verifies them through the
same shared JWTVerifier that every other microservice uses.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai4icore_auth.middleware import AuthMiddleware

from app.core.config import settings
from app.core.database import close_database, init_database
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, init_redis
from app.core.security import key_manager
from app.dependencies.auth import get_jwt_verifier, init_jwt_verifier
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routes import api_router
from app.services.cache_service import CacheService


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
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
        api_permissions_db=settings.redis_db_api_permissions,
        role_permissions_db=settings.redis_db_role_permissions,
        api_keys_db=settings.redis_db_api_keys,
        refresh_tokens_db=settings.redis_db_refresh_tokens,
    )
    await key_manager.initialize()
    await init_jwt_verifier()

    # Load API-to-permission mapping
    await _load_api_permissions()

    # Casbin RBAC policies
    try:
        from app.casbin.enforcer import load_policies_from_db
        from app.core.database import get_db

        async for db in get_db():
            await load_policies_from_db(db)
            break
        logger.info("Casbin RBAC policies loaded from database.")
    except ImportError:
        logger.info("Casbin module not available, skipping.")
    except (RuntimeError, OSError) as exc:
        logger.warning("Casbin policy loading failed: %s", exc)

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


# Module-level permission checker — set during startup, used by endpoint guard
_permission_checker = None


def get_permission_checker():
    return _permission_checker


async def _load_api_permissions() -> None:
    """
    Load api_permissions.json, resolve permission names → DB IDs,
    cache {endpoint → permission_id (int)} in Redis.

    JSON stores human-readable permission names (asr.inference).
    Startup resolves name → DB integer ID (one query).
    Guard checks integer ID against permission_ids in JWT (zero DB at request time).
    """
    global _permission_checker
    import json
    import pathlib
    from ai4icore_auth.permission_checker import PermissionChecker
    from app.core.redis import (
        get_redis_client_api_keys,
        get_redis_client_api_permissions,
        get_redis_client_refresh_tokens,
        get_redis_client_role_permissions,
    )
    from app.core.database import get_db
    from sqlalchemy import select
    from app.models.role import Permission

    json_path = pathlib.Path(__file__).parent.parent / "api_permissions.json"
    if not json_path.exists():
        logger.info("No api_permissions.json found, skipping.")
        return

    try:
        redis_api_permissions = get_redis_client_api_permissions()
        data = json.loads(json_path.read_text())

        # One DB query: permission name → DB ID
        name_to_id: dict[str, int] = {}
        async for db in get_db():
            result = await db.execute(select(Permission.name, Permission.id))
            for name, pid in result.all():
                name_to_id[name] = pid
            break

        # Resolve endpoint → permission_id (int stored as str for Redis compat)
        endpoint_to_id: dict[str, str] = {}
        for m in data.get("apiMappings", []):
            perm_name = m.get("permissionRequired")
            if perm_name is None:
                continue
            perm_id = name_to_id.get(perm_name)
            if perm_id is not None:
                endpoint_to_id[m["endpoint"]] = str(perm_id)
            else:
                logger.warning("Permission '%s' not found in DB, skipping.", perm_name)

        checker = PermissionChecker(redis_client=redis_api_permissions)
        cache_service = CacheService(
            redis_api_keys=get_redis_client_api_keys(),
            redis_refresh_tokens=get_redis_client_refresh_tokens(),
            redis_role_permissions=get_redis_client_role_permissions(),
            redis_api_permissions=redis_api_permissions,
        )
        await cache_service.cache_api_permission_map(endpoint_to_id)
        checker._api_permission_map = endpoint_to_id
        _permission_checker = checker

        logger.info("API permission mapping loaded: %d endpoints → DB IDs.", len(endpoint_to_id))
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.warning("Failed to load API permission mapping: %s", exc)


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
