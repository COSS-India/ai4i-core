"""Language Diarization Service -- FastAPI application factory."""

import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import redis as redis_sync
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai4icore_env import app_env
from ai4icore_exceptions import register_exception_handlers
from ai4icore_model_management import ModelManagementPlugin, ModelManagementConfig, AuthContextMiddleware
from ai4icore_multi_tenant import MultiTenantPlugin, MultiTenantConfig
from ai4icore_service_base import ServiceRegistryClient, RateLimitMiddleware

from app.models import Base

# Optional plugins
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
    from ai4icore_logging import get_logger, LoggingConfig, register_logging_plugin
    _LOGGING = True
except ImportError:
    _LOGGING = False

if _LOGGING:
    logger = get_logger(__name__)
    # Suppress uvicorn access logger
    _uv = logging.getLogger("uvicorn.access")
    _uv.handlers.clear()
    _uv.propagate = False
    _uv.disabled = True
else:
    logging.basicConfig(level=app_env.log_level)
    logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Starting Language Diarization Service...")

    # -- Redis (async) --
    redis_client = None
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
            logger.info("Redis connected")
            break
        except Exception as e:
            logger.warning("Redis attempt %d failed: %s", attempt + 1, e)
            if redis_client:
                await redis_client.close()
            redis_client = None
            if attempt < 2:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                logger.warning("Proceeding without Redis")

    # -- PostgreSQL --
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
    db_session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with db_engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("PostgreSQL connected")

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # -- Store in app.state --
    app.state.redis_client = redis_client
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    app.state.triton_api_key = app_env.triton_api_key
    app.state.triton_timeout = getattr(app_env, "triton_timeout", 300.0)

    # -- Service Registry --
    registry_client = ServiceRegistryClient(base_url=app_env.config_service_url)
    service_name = app_env.service_name
    service_port = app_env.service_port
    public_url = app_env.service_public_url
    if public_url:
        service_url = public_url.rstrip("/")
    else:
        service_url = f"http://{app_env.service_host}:{service_port}"

    instance_id = await registry_client.register(
        service_name=service_name,
        service_url=service_url,
        health_check_url=f"{service_url}/health",
        service_metadata={"instance_id": app_env.service_instance_id, "status": "healthy"},
    )
    if instance_id:
        logger.info("Registered %s as instance %s", service_name, instance_id)

    logger.info("Language Diarization Service started")
    yield

    # -- Shutdown --
    logger.info("Shutting down Language Diarization Service...")
    if instance_id:
        await registry_client.deregister(service_name, instance_id)
    if redis_client:
        await redis_client.close()
    if db_engine:
        await db_engine.dispose()
    if hasattr(app.state, "tenant_schema_router") and app.state.tenant_schema_router:
        await app.state.tenant_schema_router.close_all()
    logger.info("Language Diarization Service stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="Language Diarization Service",
        version="1.0.0",
        description=(
            "Language Diarization microservice using Triton Inference Server. "
            "Identifies different languages in audio and returns their segments with confidence scores."
        ),
        lifespan=lifespan,
    )

    # -- Observability --
    if _OBSERVABILITY:
        try:
            config = PluginConfig.from_env()
            config.enabled = True
            config.apps = config.apps or ["language-diarization"]
            ObservabilityPlugin(config).register_plugin(application)
        except Exception as e:
            logger.warning("Observability plugin failed: %s", e)

    # -- Tracing --
    if _TELEMETRY:
        try:
            if setup_tracing("language-diarization-service"):
                FastAPIInstrumentor.instrument_app(
                    application,
                    excluded_urls="/health,/metrics,/docs,/redoc,/openapi.json",
                )
        except Exception as e:
            logger.warning("Tracing setup failed: %s", e)

    # -- Sync Redis for Model Management Plugin --
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

    # -- Model Management Plugin --
    try:
        mm_config = ModelManagementConfig(
            model_management_service_url=app_env.model_management_service_url,
            model_management_api_key=app_env.model_management_service_api_key,
            cache_ttl_seconds=300,
            triton_endpoint_cache_ttl=300,
            default_triton_endpoint="",
            default_triton_api_key=app_env.triton_api_key,
            middleware_enabled=True,
            middleware_paths=["/api/v1/language-diarization"],
            request_timeout=10.0,
        )
        ModelManagementPlugin(config=mm_config).register_plugin(application, redis_client=redis_sync_client)
        application.add_middleware(AuthContextMiddleware, path_prefixes=["/api/v1/language-diarization"])
    except Exception as e:
        logger.warning("Model Management plugin failed: %s", e)

    # -- CORS --
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Logging Plugin --
    if _LOGGING:
        try:
            cfg = LoggingConfig.from_env()
            cfg.service_name = app_env.service_name
            cfg.use_kafka = app_env.use_kafka_logging
            register_logging_plugin(application, config=cfg)
        except Exception as e:
            logger.warning("Logging plugin failed: %s", e)

    # -- Rate Limiting --
    application.add_middleware(
        RateLimitMiddleware,
        redis_client=None,  # Picked from app.state at runtime
        requests_per_minute=app_env.rate_limit_per_minute,
        requests_per_hour=app_env.rate_limit_per_hour,
    )

    # -- Exception Handlers --
    register_exception_handlers(application)

    # -- Multi-Tenant --
    mt_config = MultiTenantConfig.from_env()
    mt_config.tenant_paths = ["/api/v1/language-diarization"]
    MultiTenantPlugin(mt_config).register_plugin(
        application,
        multi_tenant_db_url=app_env.get_multi_tenant_db_url() or app_env.get_database_url(),
    )

    # -- Routes --
    from app.routes import api_router
    application.include_router(api_router)

    # -- Root endpoint --
    @application.get("/", tags=["Health"])
    async def root():
        return {"service": "language-diarization-service", "version": "1.0.0", "status": "running"}

    return application


app = create_app()
