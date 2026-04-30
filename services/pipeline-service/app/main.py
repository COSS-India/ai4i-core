"""Pipeline Service -- FastAPI application factory."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai4icore_env import app_env
from ai4icore_exceptions import register_exception_handlers
from ai4icore_service_base import RateLimitMiddleware, ServiceRegistryClient

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
    logger.info("Starting Pipeline Service...")

    # -- Redis (async) with retry --
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

    app.state.redis_client = redis_client

    # -- Service Registry --
    registry_client = ServiceRegistryClient(base_url=app_env.config_service_url)
    service_name = app_env.service_name or "pipeline-service"
    service_port = app_env.service_port
    public_url = app_env.service_public_url
    if public_url:
        service_url = public_url.rstrip("/")
    else:
        service_url = f"http://{app_env.service_host or service_name}:{service_port}"

    instance_id = await registry_client.register(
        service_name=service_name,
        service_url=service_url,
        health_check_url=f"{service_url}/health",
        service_metadata={"instance_id": app_env.service_instance_id, "status": "healthy"},
    )
    if instance_id:
        logger.info("Registered %s as instance %s", service_name, instance_id)

    logger.info("Pipeline Service started")
    yield

    # -- Shutdown --
    logger.info("Shutting down Pipeline Service...")
    if instance_id:
        await registry_client.deregister(service_name, instance_id)
    if redis_client:
        await redis_client.close()
    logger.info("Pipeline Service stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="Pipeline Service",
        version="1.0.0",
        description="Multi-task AI pipeline orchestration microservice.",
        lifespan=lifespan,
    )

    # -- Observability --
    if _OBSERVABILITY:
        try:
            config = PluginConfig.from_env()
            config.enabled = True
            config.apps = config.apps or ["pipeline"]
            ObservabilityPlugin(config).register_plugin(application)
        except Exception as e:
            logger.warning("Observability plugin failed: %s", e)

    # -- Tracing --
    if _TELEMETRY:
        try:
            if setup_tracing("pipeline-service"):
                FastAPIInstrumentor.instrument_app(
                    application,
                    excluded_urls="/health,/metrics,/docs,/redoc,/openapi.json",
                )
        except Exception as e:
            logger.warning("Tracing setup failed: %s", e)

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
        redis_client=None,
        requests_per_minute=app_env.rate_limit_per_minute,
        requests_per_hour=app_env.rate_limit_per_hour,
    )

    # -- Exception Handlers --
    register_exception_handlers(application)

    # -- Multi-Tenant --
    try:
        from ai4icore_multi_tenant import MultiTenantPlugin, MultiTenantConfig
        mt_config = MultiTenantConfig.from_env()
        mt_config.tenant_paths = ["/api/v1/pipeline"]
        MultiTenantPlugin(mt_config).register_plugin(
            application,
            multi_tenant_db_url=app_env.get_multi_tenant_db_url() or app_env.get_database_url(),
        )
    except Exception as e:
        logger.warning("Multi-Tenant plugin failed: %s", e)

    # -- Routes --
    from app.routes import api_router
    application.include_router(api_router)

    # -- Root endpoint --
    @application.get("/", tags=["Health"])
    async def root():
        return {"service": "pipeline-service", "version": "1.0.0", "status": "running"}

    return application


app = create_app()
