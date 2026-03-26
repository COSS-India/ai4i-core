"""
Language Diarization Service - Language Diarization microservice

Main FastAPI application entry point for the Language Diarization microservice.
Provides batch language diarization inference using Triton Inference Server.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

# Libs are pip-installed in editable mode; bind mounts update source in place.

import redis.asyncio as redis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai4icore_env import app_env
from ai4icore_observability import ObservabilityPlugin, PluginConfig
from ai4icore_model_management import ModelManagementPlugin, ModelManagementConfig, AuthContextMiddleware

# Logging imports (structured JSON logging to OpenSearch via ai4icore_logging)
LOGGING_AVAILABLE = False
get_logger = None
LoggingConfig = None
register_logging_plugin = None
try:
    from ai4icore_logging import get_logger, LoggingConfig, register_logging_plugin
    LOGGING_AVAILABLE = True
except ImportError:
    pass

# Tracing imports (OpenTelemetry for distributed tracing)
TRACING_AVAILABLE = False
setup_tracing = None
FastAPIInstrumentor = None
try:
    from ai4icore_telemetry import setup_tracing
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    TRACING_AVAILABLE = True
except ImportError:
    pass

from routers import inference_router
from models import database_models, auth_models
from utils.service_registry_client import ServiceRegistryHttpClient
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.error_handler_middleware import add_error_handlers
from ai4icore_exceptions import register_exception_handlers
from ai4icore_multi_tenant import MultiTenantPlugin, MultiTenantConfig
from utils.triton_client import TritonClient

# Configure structured logging (JSON) so Fluent Bit can forward logs to OpenSearch.
# Fallback to basic logging if ai4icore_logging is not available.
if LOGGING_AVAILABLE:
    logger = get_logger(__name__)

    # Disable uvicorn access logger to avoid duplicate plain-text logs
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True
    uvicorn_access.setLevel(logging.CRITICAL + 1)
else:
    logging.basicConfig(
        level=app_env.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

REDIS_HOST = app_env.redis_host
REDIS_PORT = app_env.redis_port
REDIS_PASSWORD = app_env.redis_password
REDIS_TIMEOUT = app_env.redis_timeout

DATABASE_URL = app_env.get_database_url()

# Multi-tenant database URL for tenant schema routing
MULTI_TENANT_DB_URL = app_env.get_multi_tenant_db_url()

TRITON_ENDPOINT = app_env.triton_endpoint or ""
TRITON_API_KEY = app_env.triton_api_key
TRITON_TIMEOUT = app_env.triton_timeout

redis_client: Optional[redis.Redis] = None
db_engine: Optional[AsyncEngine] = None
db_session_factory: Optional[async_sessionmaker] = None
registry_client: Optional[ServiceRegistryHttpClient] = None
registered_instance_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, db_engine, db_session_factory, registry_client, registered_instance_id

    logger.info("Starting Language Diarization Service...")

    # Redis
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            logger.info(
                "Connecting to Redis at %s:%s (attempt %s/%s)...",
                REDIS_HOST,
                REDIS_PORT,
                attempt + 1,
                max_retries,
            )
            redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=REDIS_TIMEOUT,
                socket_timeout=REDIS_TIMEOUT,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            await redis_client.ping()
            logger.info("Redis connection established successfully")
            break
        except Exception as e:
            logger.warning("Redis connection attempt %s failed: %s", attempt + 1, e)
            if redis_client:
                try:
                    await redis_client.close()
                except Exception:
                    pass
                redis_client = None
            if attempt < max_retries - 1:
                logger.info("Retrying Redis connection in %s seconds...", retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.warning("Proceeding without Redis (rate limiting disabled)")
                redis_client = None

    # Postgres
    try:
        logger.info("Connecting to PostgreSQL...")
        db_engine = create_async_engine(
            DATABASE_URL,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
            connect_args={"timeout": 30, "command_timeout": 30},
        )
        db_session_factory = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )

        logger.info("Testing PostgreSQL connection...")
        try:
            async with asyncio.timeout(60):
                async with db_engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
        except asyncio.TimeoutError:
            raise Exception("PostgreSQL connection timeout after 60 seconds")

        logger.info("PostgreSQL connection established successfully")
        
        # Create tables if they do not exist
        try:
            async with db_engine.begin() as conn:
                await conn.run_sync(database_models.Base.metadata.create_all)
            logger.info("✓ Database tables verified/created successfully")
        except Exception as e:
            logger.error("❌ Failed to create database tables: %s", e)
            raise
    except Exception as e:
        logger.error("Failed to connect to PostgreSQL: %s", e)
        raise

    app.state.redis_client = redis_client
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    
    # Tenant schema router is created by MultiTenantPlugin at registration time
    
    app.state.triton_endpoint = TRITON_ENDPOINT
    app.state.triton_api_key = TRITON_API_KEY
    app.state.triton_timeout = TRITON_TIMEOUT

    # Service registry
    try:
        registry_client = ServiceRegistryHttpClient()
        service_name = app_env.service_name or "language-diarization-service"
        service_port = app_env.service_port
        public_base_url = app_env.service_public_url
        if public_base_url:
            service_url = public_base_url.rstrip("/")
        else:
            service_host = app_env.service_host or service_name
            service_url = f"http://{service_host}:{service_port}"
        health_url = service_url + "/health"
        instance_id = app_env.service_instance_id or f"{service_name}-{os.getpid()}"
        registered_instance_id = await registry_client.register(
            service_name=service_name,
            service_url=service_url,
            health_check_url=health_url,
            service_metadata={"instance_id": instance_id, "status": "healthy"},
        )
        if registered_instance_id:
            logger.info(
                "Registered %s with service registry as instance %s",
                service_name,
                registered_instance_id,
            )
        else:
            logger.warning(
                "Service registry registration skipped/failed for %s", service_name
            )
    except Exception as e:
        logger.warning("Service registry registration error: %s", e)

    logger.info("Language Diarization Service started successfully")

    yield

    logger.info("Shutting down Language Diarization Service...")
    try:
        try:
            if registry_client and registered_instance_id:
                service_name = app_env.service_name or "language-diarization-service"
                await registry_client.deregister(service_name, registered_instance_id)
        except Exception as e:
            logger.warning("Service registry deregistration error: %s", e)

        if redis_client:
            await redis_client.close()
            logger.info("Redis connection closed")

        if db_engine:
            await db_engine.dispose()
            logger.info("PostgreSQL connection closed")

        tenant_router = getattr(app.state, "tenant_schema_router", None)
        if tenant_router:
            await tenant_router.close_all()
            logger.info("Tenant schema router connections closed")
    except Exception as e:
        logger.error("Error during shutdown: %s", e)


app = FastAPI(
    title="Language Diarization Service",
    version="1.0.0",
    description=(
        "Language Diarization microservice using Triton Inference Server. "
        "Identifies different languages in audio and returns their segments with confidence scores."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Language Diarization Inference", "description": "Language diarization inference endpoints"},
        {"name": "Health", "description": "Service health and readiness checks"},
    ],
    lifespan=lifespan,
)

# Observability
obs_config = PluginConfig.from_env()
obs_config.enabled = True
if not obs_config.customers:
    obs_config.customers = []
if not obs_config.apps:
    obs_config.apps = ["language-diarization"]

observability_plugin = ObservabilityPlugin(obs_config)
observability_plugin.register_plugin(app)
logger.info("AI4ICore Observability Plugin initialized for Language Diarization service")

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
if TRACING_AVAILABLE:
    tracer = setup_tracing("language-diarization-service")
    if tracer:
        logger.info("✅ Distributed tracing initialized for Language Diarization service")
        # Instrument FastAPI to automatically create spans for all requests
        FastAPIInstrumentor.instrument_app(app)
        logger.info("✅ FastAPI instrumentation enabled for tracing")
    else:
        logger.warning("⚠️ Tracing not available (OpenTelemetry setup failed)")
else:
    logger.warning("⚠️ Tracing not available (OpenTelemetry may not be installed)")

# Model Management Plugin - single source of truth for Triton endpoint/model (no env fallback)
try:
    mm_config = ModelManagementConfig(
        model_management_service_url=app_env.model_management_service_url,
        model_management_api_key=app_env.model_management_service_api_key,
        cache_ttl_seconds=300,
        triton_endpoint_cache_ttl=300,
        default_triton_endpoint="",
        default_triton_api_key="",
        middleware_enabled=True,
        middleware_paths=["/api/v1/language-diarization"],
        request_timeout=10.0,
    )
    model_mgmt_plugin = ModelManagementPlugin(config=mm_config)
    model_mgmt_plugin.register_plugin(app, redis_client=None)
    app.add_middleware(AuthContextMiddleware, path_prefixes=mm_config.middleware_paths or ["/api/v1/language-diarization"])
    logger.info("✅ Model Management Plugin initialized for Language Diarization service")
except Exception as e:
    logger.warning(f"Failed to initialize Model Management Plugin: {e}")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize AI4ICore Logging Plugin
if LOGGING_AVAILABLE and register_logging_plugin and LoggingConfig:
    logging_config = LoggingConfig.from_env()
    logging_config.service_name = app_env.service_name
    logging_config.use_kafka = app_env.use_kafka_logging
    register_logging_plugin(app, config=logging_config)
    logger.info("✅ AI4ICore Logging Plugin initialized for Language Diarization service")

# Rate limiting (Redis client will be picked from app.state)
rate_limit_per_minute = app_env.rate_limit_per_minute
rate_limit_per_hour = app_env.rate_limit_per_hour
app.add_middleware(
    RateLimitMiddleware,
    redis_client=None,
    requests_per_minute=rate_limit_per_minute,
    requests_per_hour=rate_limit_per_hour,
)

# Error handlers
register_exception_handlers(app)
add_error_handlers(app)

# Multi-tenant plugin (tenant schema router + middleware)
multi_tenant_db_url = MULTI_TENANT_DB_URL or DATABASE_URL
multi_tenant_config = MultiTenantConfig.from_env()
multi_tenant_config.tenant_paths = ["/api/v1/language-diarization"]
multi_tenant_plugin = MultiTenantPlugin(multi_tenant_config)
multi_tenant_plugin.register_plugin(app, multi_tenant_db_url=multi_tenant_db_url)
logger.info("✅ AI4ICore Multi-Tenant Plugin initialized for Language Diarization service")

# Routers
app.include_router(inference_router.inference_router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "language-diarization-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Language Diarization microservice",
    }


@app.get("/health", tags=["Health"])
async def health(request: Request):
    redis_ok = False
    db_ok = False
    triton_ok = False

    # Check if health logs should be excluded
    exclude_health_logs = app_env.exclude_health_logs
    
    try:
        rc = getattr(request.app.state, "redis_client", None)
        if rc is not None:
            await rc.ping()
            redis_ok = True
    except Exception as e:
        if not exclude_health_logs:
            logger.warning("/health: Redis check failed: %s", e)

    try:
        session_factory = getattr(request.app.state, "db_session_factory", None)
        if session_factory is not None:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        if not exclude_health_logs:
            logger.warning("/health: PostgreSQL check failed: %s", e)

    try:
        triton_endpoint = getattr(request.app.state, "triton_endpoint", "")
        if triton_endpoint:
            triton_client_instance = TritonClient(triton_endpoint)
            if triton_client_instance.client.is_server_live() and triton_client_instance.client.is_server_ready():
                triton_ok = True
    except Exception as e:
        if not exclude_health_logs:
            logger.warning("/health: Triton check failed: %s", e)

    status_str = "ok" if (redis_ok and db_ok and triton_ok) else "degraded"
    status_code = 200 if status_str == "ok" else 503

    return {
        "service": "language-diarization-service",
        "status": status_str,
        "redis_ok": redis_ok,
        "db_ok": db_ok,
        "triton_ok": triton_ok,
        "version": "1.0.0",
    }, status_code


if __name__ == "__main__":
    import uvicorn

    port = app_env.service_port
    log_level = app_env.log_level.lower()

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=log_level,
        reload=False,
    )

