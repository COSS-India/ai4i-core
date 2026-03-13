"""
NMT Service - Neural Machine Translation microservice
Main FastAPI application entry point
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
import redis.asyncio as redis
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ai4icore_observability import ObservabilityPlugin, PluginConfig
from ai4icore_logging import (
    get_logger,
    LoggingConfig,
    register_logging_plugin,
)
from ai4icore_telemetry import setup_tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from ai4icore_env import app_env

# Load environment variables from .env file if it exists
load_dotenv()

from routers import health_router, inference_router, try_it_router
from utils.service_registry_client import ServiceRegistryHttpClient
from utils.triton_client import TritonClient
from utils.model_management_client import ModelManagementClient
from ai4icore_model_management import ModelManagementPlugin, ModelManagementConfig, AuthContextMiddleware
from middleware.auth_provider import AuthProvider
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.error_handler_middleware import add_error_handlers
from ai4icore_constants.exceptions import AuthenticationError, AuthorizationError, RateLimitExceededError
from ai4icore_multi_tenant import MultiTenantPlugin, MultiTenantConfig

# Import models to ensure they are registered with SQLAlchemy
from models import database_models, auth_models

# Aggressively disable uvicorn access logger BEFORE uvicorn starts
# This must happen before uvicorn imports/creates its loggers
import logging
uvicorn_access = logging.getLogger("uvicorn.access")
uvicorn_access.handlers.clear()
uvicorn_access.propagate = False
uvicorn_access.disabled = True
uvicorn_access.setLevel(logging.CRITICAL + 1)  # Set above CRITICAL to ensure nothing logs

# Also disable at root level by filtering out uvicorn.access messages
class UvicornAccessFilter(logging.Filter):
    """Filter to block uvicorn.access log messages."""
    def filter(self, record):
        # Block uvicorn.access logger
        if record.name == "uvicorn.access":
            return False
        # Also block messages that look like uvicorn access logs
        # Format: "INFO: IP:PORT "METHOD PATH HTTP/1.1" STATUS"
        message = str(record.getMessage())
        if 'HTTP/1.1"' in message:
            import re
            # Match uvicorn access log pattern: INFO: IP:PORT "METHOD PATH HTTP/1.1" STATUS
            if re.search(r'INFO:\s+\d+\.\d+\.\d+\.\d+:\d+\s+"(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+.*HTTP/1\.1"\s+\d+', message):
                return False
        return True

# Add filter to root logger to catch any uvicorn.access messages
root_logger = logging.getLogger()
uvicorn_filter = UvicornAccessFilter()
for handler in root_logger.handlers:
    handler.addFilter(uvicorn_filter)

# Get logger instance
logger = get_logger(__name__)

# Environment variables - Support both REDIS_PORT and REDIS_PORT_NUMBER for backward compatibility
REDIS_HOST = app_env.redis_host
REDIS_PORT = app_env.redis_port
REDIS_PASSWORD = app_env.redis_password
REDIS_TIMEOUT = app_env.redis_timeout
DATABASE_URL = app_env.get_database_url()

# Multi-tenant database URL for tenant schema routing
MULTI_TENANT_DB_URL = app_env.get_multi_tenant_db_url()

# NOTE: Triton endpoint/model MUST come from Model Management for inference.
# No environment variable fallback - all resolution via Model Management database.
MODEL_MANAGEMENT_SERVICE_URL = app_env.model_management_service_url
MODEL_MANAGEMENT_SERVICE_API_KEY = app_env.model_management_service_api_key or app_env.model_management_api_key
MODEL_MANAGEMENT_CACHE_TTL = app_env.model_management_cache_ttl
TRITON_ENDPOINT_CACHE_TTL = app_env.triton_endpoint_cache_ttl
SMR_SERVICE_URL = app_env.smr_service_url

# Global variables
redis_client: Optional[redis.Redis] = None
db_engine: Optional[AsyncEngine] = None
db_session_factory: Optional[async_sessionmaker] = None
registry_client: Optional[ServiceRegistryHttpClient] = None
registered_instance_id: Optional[str] = None

logger.info(f"Configuration loaded: REDIS_HOST={REDIS_HOST}, REDIS_PORT={REDIS_PORT}")
logger.info(f"DATABASE_URL configured: {DATABASE_URL.split('@')[0]}@***")  # Mask password in logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown"""
    global redis_client, db_engine, db_session_factory, registry_client, registered_instance_id

    # Disable uvicorn access logger AFTER uvicorn has started
    # This ensures it stays disabled even if uvicorn recreates loggers
    import logging
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True
    uvicorn_access.setLevel(logging.CRITICAL)  # Extra safety - set to highest level

    # Startup
    logger.info("Starting NMT Service...")

    # Initialize Redis with retry logic
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            logger.info(
                f"Attempting to connect to Redis at {REDIS_HOST}:{REDIS_PORT} "
                f"(attempt {attempt + 1}/{max_retries})..."
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

            # Test Redis connection
            await redis_client.ping()
            logger.info("✓ Redis connection established successfully")
            break

        except Exception as e:
            logger.warning(f"Redis connection attempt {attempt + 1}/{max_retries} failed: {e}")

            if redis_client:
                try:
                    await redis_client.close()
                except Exception:
                    pass
                redis_client = None

            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.warning(
                    "⚠ Redis connection failed after all retries. "
                    "Proceeding without Redis (rate limiting disabled)"
                )
                redis_client = None

    # Initialize PostgreSQL
    try:
        logger.info("Connecting to PostgreSQL...")
        logger.info(f"Using DATABASE_URL: {DATABASE_URL.split('@')[0]}@***")  # Mask password in logs

        db_engine = create_async_engine(
            DATABASE_URL,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,  # Test connections before using them
            pool_recycle=3600,   # Recycle connections after 1 hour
            echo=False,
            connect_args={
                "timeout": 30,
                "command_timeout": 30,
            },
        )

        db_session_factory = async_sessionmaker(
            db_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Test database connection with timeout
        logger.info("Testing PostgreSQL connection...")
        try:
            async with asyncio.timeout(60):
                async with db_engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
        except asyncio.TimeoutError:
            raise Exception("PostgreSQL connection timeout after 60 seconds")

        logger.info("✓ PostgreSQL connection established successfully")

    except Exception as e:
        logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
        raise

    # Store in app state for middleware & routes
    app.state.redis_client = redis_client
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    
    # Tenant schema router is created by MultiTenantPlugin at registration time
    # (uses MULTI_TENANT_DB_URL or DATABASE_URL fallback)
    
    # Create Model Management client and store in app state
    # NOTE: Triton endpoint/model MUST come from Model Management for inference.
    # No environment variable fallback - all resolution via Model Management database.
    model_management_client = ModelManagementClient(
        base_url=MODEL_MANAGEMENT_SERVICE_URL,
        api_key=MODEL_MANAGEMENT_SERVICE_API_KEY,
        cache_ttl_seconds=MODEL_MANAGEMENT_CACHE_TTL
    )
    app.state.model_management_client = model_management_client
    
    # NOTE: Model Management Plugin is registered BEFORE app starts (see line ~320)
    # to avoid "Cannot add middleware after application has started" error

    # Register service into the central registry via config-service
    try:
        registry_client = ServiceRegistryHttpClient()
        service_name = app_env.service_name or "nmt-service"
        service_port = app_env.service_port
        # Prefer explicit public base URL if provided
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
            logger.info("Registered %s with service registry as instance %s", service_name, registered_instance_id)
        else:
            logger.warning("Service registry registration skipped/failed for %s", service_name)
    except Exception as e:
        logger.warning("Service registry registration error: %s", e)

    logger.info("✅ NMT Service started successfully")

    # ---- Application is now up ----
    yield

    # Shutdown
    logger.info("Shutting down NMT Service...")

    try:
        # Deregister from registry if previously registered
        try:
            if registry_client and registered_instance_id:
                service_name = app_env.service_name or "nmt-service"
                await registry_client.deregister(service_name, registered_instance_id)
        except Exception as e:
            logger.warning("Service registry deregistration error: %s", e)

        if redis_client:
            await redis_client.close()
            logger.info("Redis connection closed")

        if db_engine:
            await db_engine.dispose()
            logger.info("PostgreSQL connection closed")
        
        # Close tenant schema router connections
        tenant_router = getattr(app.state, 'tenant_schema_router', None)
        if tenant_router:
            await tenant_router.close_all()
            logger.info("Tenant schema router connections closed")
        
        if model_management_client:
            await model_management_client.close()
            logger.info("Model Management Service client closed")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

    logger.info("NMT Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="NMT Service",
    version="1.0.2",
    description=(
        "Neural Machine Translation microservice for translating text between 22+ Indic languages. "
        "Supports bidirectional translation with script code handling and batch processing."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "NMT Inference",
            "description": "Neural machine translation endpoints",
        },
        {
            "name": "Models",
            "description": "Translation model and language pair management",
        },
        {
            "name": "Health",
            "description": "Service health and readiness checks",
        },
    ],
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize AI4ICore Logging Plugin
# Register before observability to preserve existing middleware ordering behavior.
logging_config = LoggingConfig.from_env()
logging_config.service_name = app_env.service_name or None
logging_config.use_kafka = app_env.use_kafka_logging
register_logging_plugin(app, config=logging_config)
logger.info("✅ AI4ICore Logging Plugin initialized for NMT service")

# Observability (MUST be added AFTER RequestLoggingMiddleware)
# FastAPI middleware runs in REVERSE order, so this will run FIRST
# This ensures organization is extracted and set in context before RequestLoggingMiddleware logs
config = PluginConfig.from_env()
config.enabled = True  # Enable plugin
config.debug = False  # Disable debug print statements - use structured logging instead
if not config.customers:
    config.customers = []  # Will be extracted from JWT/headers automatically
if not config.apps:
    config.apps = ["nmt"]  # Service name

plugin = ObservabilityPlugin(config)
plugin.register_plugin(app)
logger.info("✅ AI4ICore Observability Plugin initialized for NMT service")

# Initialize Redis client early for middleware (synchronous for Model Management Plugin)
import redis as redis_sync
redis_client_sync = None
try:
    redis_client_sync = redis_sync.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True
    )
    # Test Redis connection (synchronous ping)
    redis_client_sync.ping()
    logger.info("Redis client created for middleware (connection tested)")
except Exception as e:
    logger.warning(f"Redis connection failed for middleware: {e}")
    redis_client_sync = None

# Model Management Plugin - single source of truth for Triton endpoint/model (no env fallback)
# MUST be registered BEFORE app starts (before other middleware) to avoid "Cannot add middleware after application has started" error
model_mgmt_config = ModelManagementConfig(
    model_management_service_url=MODEL_MANAGEMENT_SERVICE_URL,
    model_management_api_key=MODEL_MANAGEMENT_SERVICE_API_KEY,
    cache_ttl_seconds=MODEL_MANAGEMENT_CACHE_TTL,
    triton_endpoint_cache_ttl=TRITON_ENDPOINT_CACHE_TTL,
    default_triton_endpoint="",  # No fallback - must come from Model Management
    default_triton_api_key="",  # No fallback - must come from Model Management
    middleware_enabled=True,
    middleware_paths=["/api/v1"]
)
model_mgmt_plugin = ModelManagementPlugin(model_mgmt_config)
model_mgmt_plugin.register_plugin(app, redis_client=redis_client_sync)
app.add_middleware(AuthContextMiddleware, path_prefixes=model_mgmt_config.middleware_paths or ["/api/v1"])
logger.info("✅ Model Management Plugin initialized for NMT service")

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
tracer = setup_tracing("nmt-service")
if tracer:
    logger.info("✅ Distributed tracing initialized for NMT service")
    # Instrument FastAPI to automatically create spans for all requests
    FastAPIInstrumentor.instrument_app(app)
    logger.info("✅ FastAPI instrumentation enabled for tracing")
else:
    logger.warning("⚠️ Tracing not available (OpenTelemetry may not be installed)")

# Multi-tenant plugin (tenant context, schema routing)
multi_tenant_config = MultiTenantConfig.from_env()
multi_tenant_config.tenant_paths = ["/api/v1/nmt"]
multi_tenant_plugin = MultiTenantPlugin(multi_tenant_config)
multi_tenant_plugin.register_plugin(
    app,
    multi_tenant_db_url=MULTI_TENANT_DB_URL or DATABASE_URL,  # db_settings handles both
)
logger.info("✅ AI4ICore Multi-Tenant Plugin initialized for NMT service")

# Add rate limiting middleware (will use app.state.redis_client when available)
rate_limit_per_minute = app_env.rate_limit_per_minute
rate_limit_per_hour = app_env.rate_limit_per_hour
app.add_middleware(
    RateLimitMiddleware,
    redis_client=None,  # Will use app.state.redis_client as fallback
    requests_per_minute=rate_limit_per_minute,
    requests_per_hour=rate_limit_per_hour,
)

# Register error handlers
add_error_handlers(app)

# Include routers
app.include_router(inference_router)
app.include_router(try_it_router)
app.include_router(health_router)


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint"""
    return {
        "service": "nmt-service",
        "version": "1.0.2",
        "status": "running",
        "description": "Neural Machine Translation microservice",
        "redis_available": getattr(app.state, "redis_client", None) is not None,
        "redis_host": REDIS_HOST,
    }


@app.get("/health", tags=["Health"])
async def health(request: Request):
    """
    Simple health endpoint for Kubernetes readiness/liveness probes.

    Returns:
    - 200 when core dependencies are OK
    - 503 when degraded (e.g. DB or Redis down)
    """
    redis_ok = False
    db_ok = False

    # Check Redis
    # Check if health logs should be excluded
    exclude_health_logs = app_env.exclude_health_logs
    
    try:
        rc = getattr(request.app.state, "redis_client", None)
        if rc is not None:
            await rc.ping()
            redis_ok = True
    except Exception as e:
        if not exclude_health_logs:
            logger.warning(f"/health: Redis check failed: {e}")

    # Check DB
    try:
        session_factory = getattr(request.app.state, "db_session_factory", None)
        if session_factory is not None:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        if not exclude_health_logs:
            logger.warning(f"/health: PostgreSQL check failed: {e}")

    status_str = "ok" if (redis_ok and db_ok) else "degraded"
    status_code = 200 if status_str == "ok" else 503

    return {
        "service": "nmt-service",
        "status": status_str,
        "redis_ok": redis_ok,
        "db_ok": db_ok,
        "version": "1.0.2",
    }, status_code


if __name__ == "__main__":
    port = app_env.service_port
    log_level = app_env.log_level.lower()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=log_level,
        reload=False,
    )
