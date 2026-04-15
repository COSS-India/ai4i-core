"""
Shared FastAPI application factory for AI4I-Core inference services.

Eliminates ~250 lines of duplicated boilerplate per service.
Each service only needs to provide its config and routes.

Usage::

    from ai4icore_service_base import create_inference_app
    from app.routes import api_router
    from app.models import Base

    app = create_inference_app(
        service_name="ner-service",
        title="NER Service",
        description="Named Entity Recognition microservice.",
        api_prefix="/api/v1/ner",
        router=api_router,
        db_base=Base,
    )
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
import redis as redis_sync
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai4icore_env import app_env
from ai4icore_exceptions import register_exception_handlers
from ai4icore_model_management import (
    AuthContextMiddleware,
    ModelManagementConfig,
    ModelManagementPlugin,
)
from ai4icore_multi_tenant import MultiTenantConfig, MultiTenantPlugin

from .rate_limit import RateLimitMiddleware
from .service_registry import ServiceRegistryClient

# ---------------------------------------------------------------------------
# Optional plugins -- graceful degradation when not installed
# ---------------------------------------------------------------------------
try:
    from ai4icore_observability import ObservabilityPlugin, PluginConfig

    _OBSERVABILITY = True
except ImportError:
    _OBSERVABILITY = False

try:
    from ai4icore_telemetry import setup_tracing
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _TELEMETRY = True
except ImportError:
    _TELEMETRY = False

try:
    from ai4icore_logging import LoggingConfig, get_logger, register_logging_plugin

    _LOGGING = True
except ImportError:
    _LOGGING = False


def _init_logger(name: str) -> logging.Logger:
    """Return a logger, preferring the structured ai4icore_logging variant."""
    if _LOGGING:
        _logger = get_logger(name)
        # Suppress noisy uvicorn access logger
        _uv = logging.getLogger("uvicorn.access")
        _uv.handlers.clear()
        _uv.propagate = False
        _uv.disabled = True
        return _logger
    logging.basicConfig(level=app_env.log_level)
    return logging.getLogger(name)


logger = _init_logger(__name__)


# ---------------------------------------------------------------------------
# Service configuration dataclass
# ---------------------------------------------------------------------------
@dataclass
class InferenceServiceConfig:
    """All the knobs a service can turn when calling ``create_inference_app``."""

    # Identity
    service_name: str
    title: str
    description: str = ""
    version: str = "1.0.0"

    # API prefix -- used for middleware path filtering
    api_prefix: str = "/api/v1"

    # Extra app.state attributes set during startup
    # e.g. {"triton_timeout": 300.0, "triton_endpoint": "..."}
    extra_state: Dict[str, Any] = field(default_factory=dict)

    # Observability app tag (defaults to service_name without "-service")
    observability_app: str = ""

    # CORS
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
def _build_lifespan(config: InferenceServiceConfig, db_base: Any):
    """Return an async context manager that handles startup/shutdown."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc_logger = _init_logger(config.service_name)
        svc_logger.info("Starting %s ...", config.title)

        # ── Redis (async) with retry ──
        redis_client: Optional[aioredis.Redis] = None
        delay = 2
        for attempt in range(3):
            try:
                redis_client = aioredis.Redis(
                    host=app_env.redis_host,
                    port=app_env.redis_port,
                    password=app_env.redis_password,
                    decode_responses=True,
                    socket_connect_timeout=app_env.redis_timeout,
                    socket_timeout=app_env.redis_timeout,
                    retry_on_timeout=True,
                    health_check_interval=30,
                )
                await redis_client.ping()
                svc_logger.info("Redis connected")
                break
            except Exception as e:
                svc_logger.warning("Redis attempt %d failed: %s", attempt + 1, e)
                if redis_client:
                    await redis_client.close()
                redis_client = None
                if attempt < 2:
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    svc_logger.warning("Proceeding without Redis")

        # ── PostgreSQL ──
        db_url = app_env.get_database_url()
        db_engine = create_async_engine(
            db_url,
            pool_size=app_env.db_pool_size,
            max_overflow=app_env.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
            connect_args={"timeout": 30, "command_timeout": 30},
        )
        db_session_factory = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )

        async with db_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        svc_logger.info("PostgreSQL connected")

        async with db_engine.begin() as conn:
            await conn.run_sync(db_base.metadata.create_all)

        # ── Store in app.state ──
        app.state.redis_client = redis_client
        app.state.db_engine = db_engine
        app.state.db_session_factory = db_session_factory
        app.state.triton_api_key = app_env.triton_api_key

        # Service-specific extra state
        for key, value in config.extra_state.items():
            setattr(app.state, key, value)

        # ── Service Registry ──
        registry_client = ServiceRegistryClient(base_url=app_env.config_service_url)
        # Use the factory-provided identity as the source of truth.
        # Relying on SERVICE_NAME env var is fragile and can silently break registration.
        service_name = config.service_name
        service_port = app_env.service_port
        public_url = app_env.service_public_url
        if public_url:
            service_url = public_url.rstrip("/")
        else:
            service_host = app_env.service_host or service_name
            service_url = f"http://{service_host}:{service_port}"

        instance_id = await registry_client.register(
            service_name=service_name,
            service_url=service_url,
            health_check_url=f"{service_url}/health",
            service_metadata={
                "instance_id": app_env.service_instance_id,
                "status": "healthy",
            },
        )
        if not instance_id:
            # Config-service may not be reachable during initial startup ordering.
            # Retry a few times so services eventually appear in discovery/health snapshots.
            retry_delay = 0.5
            for _ in range(5):
                await asyncio.sleep(retry_delay)
                instance_id = await registry_client.register(
                    service_name=service_name,
                    service_url=service_url,
                    health_check_url=f"{service_url}/health",
                    service_metadata={
                        "instance_id": app_env.service_instance_id,
                        "status": "healthy",
                    },
                )
                if instance_id:
                    break
                retry_delay = min(retry_delay * 2, 5.0)
        if instance_id:
            svc_logger.info("Registered %s as instance %s", service_name, instance_id)

        svc_logger.info("%s started", config.title)
        yield

        # ── Shutdown ──
        svc_logger.info("Shutting down %s ...", config.title)
        if instance_id:
            await registry_client.deregister(service_name, instance_id)
        if redis_client:
            await redis_client.close()
        if db_engine:
            await db_engine.dispose()
        if hasattr(app.state, "tenant_schema_router") and app.state.tenant_schema_router:
            await app.state.tenant_schema_router.close_all()
        svc_logger.info("%s stopped", config.title)

    return lifespan


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def create_inference_app(
    *,
    service_name: str,
    title: str,
    description: str = "",
    version: str = "1.0.0",
    api_prefix: str = "/api/v1",
    router: APIRouter,
    db_base: Any,
    extra_state: Optional[Dict[str, Any]] = None,
    observability_app: str = "",
    cors_origins: Optional[List[str]] = None,
) -> FastAPI:
    """
    Create a fully configured FastAPI application for an inference service.

    This factory wires up: lifespan (Redis, PostgreSQL, service registry),
    observability, tracing, model management, CORS, logging, rate limiting,
    exception handlers, and multi-tenant support.

    Args:
        service_name: e.g. ``"ner-service"``
        title: Human-readable title for OpenAPI docs.
        description: OpenAPI description.
        version: Service version string.
        api_prefix: API path prefix, e.g. ``"/api/v1/ner"``.
        router: The aggregated ``APIRouter`` from ``app.routes``.
        db_base: SQLAlchemy ``declarative_base()`` from ``app.models``.
        extra_state: Additional ``app.state`` attributes set at startup.
        observability_app: Observability app tag (defaults to service_name
            minus the ``"-service"`` suffix).
        cors_origins: Allowed CORS origins (defaults to ``["*"]``).
    """
    config = InferenceServiceConfig(
        service_name=service_name,
        title=title,
        description=description,
        version=version,
        api_prefix=api_prefix,
        extra_state=extra_state or {},
        observability_app=observability_app or service_name.replace("-service", ""),
        cors_origins=cors_origins or ["*"],
    )

    application = FastAPI(
        title=config.title,
        version=config.version,
        description=config.description,
        lifespan=_build_lifespan(config, db_base),
    )

    # ── Observability ──
    if _OBSERVABILITY:
        try:
            obs_config = PluginConfig.from_env()
            obs_config.enabled = True
            obs_config.apps = obs_config.apps or [config.observability_app]
            ObservabilityPlugin(obs_config).register_plugin(application)
        except Exception as e:
            logger.warning("Observability plugin failed: %s", e)

    # ── Tracing ──
    if _TELEMETRY:
        try:
            if setup_tracing(config.service_name):
                FastAPIInstrumentor.instrument_app(
                    application,
                    excluded_urls="/health,/metrics,/docs,/redoc,/openapi.json",
                )
        except Exception as e:
            logger.warning("Tracing setup failed: %s", e)

    # ── Sync Redis for Model Management Plugin ──
    redis_sync_client = None
    try:
        redis_sync_client = redis_sync.Redis(
            host=app_env.redis_host,
            port=app_env.redis_port,
            password=app_env.redis_password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        redis_sync_client.ping()
    except Exception:
        redis_sync_client = None

    # ── Model Management Plugin ──
    try:
        mm_config = ModelManagementConfig(
            model_management_service_url=app_env.model_management_service_url,
            model_management_api_key=app_env.model_management_service_api_key,
            cache_ttl_seconds=300,
            triton_endpoint_cache_ttl=300,
            default_triton_endpoint="",
            default_triton_api_key=app_env.triton_api_key,
            middleware_enabled=True,
            middleware_paths=[config.api_prefix],
            request_timeout=10.0,
        )
        ModelManagementPlugin(config=mm_config).register_plugin(
            application, redis_client=redis_sync_client
        )
        application.add_middleware(
            AuthContextMiddleware, path_prefixes=[config.api_prefix]
        )
    except Exception as e:
        logger.warning("Model Management plugin failed: %s", e)

    # ── CORS ──
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=config.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Logging Plugin ──
    if _LOGGING:
        try:
            log_config = LoggingConfig.from_env()
            log_config.service_name = app_env.service_name
            log_config.use_kafka = app_env.use_kafka_logging
            register_logging_plugin(application, config=log_config)
        except Exception as e:
            logger.warning("Logging plugin failed: %s", e)

    # ── Inference Response Headers (X-Trace-Id, X-Inference-Model-Time) ──
    from .inference_headers import InferenceHeadersMiddleware
    application.add_middleware(InferenceHeadersMiddleware)

    # ── Rate Limiting ──
    application.add_middleware(
        RateLimitMiddleware,
        redis_client=None,
        requests_per_minute=app_env.rate_limit_per_minute,
        requests_per_hour=app_env.rate_limit_per_hour,
    )

    # ── Exception Handlers ──
    register_exception_handlers(application)

    # ── Multi-Tenant ──
    mt_config = MultiTenantConfig.from_env()
    mt_config.tenant_paths = [config.api_prefix]
    MultiTenantPlugin(mt_config).register_plugin(
        application,
        multi_tenant_db_url=app_env.get_multi_tenant_db_url() or app_env.get_database_url(),
    )

    # ── Routes ──
    application.include_router(router)

    # ── Root endpoint ──
    @application.get("/", tags=["Health"])
    async def root():
        return {
            "service": config.service_name,
            "version": config.version,
            "status": "running",
        }

    return application
