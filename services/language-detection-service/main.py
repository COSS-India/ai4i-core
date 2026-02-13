import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
import redis.asyncio as redis
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ai4icore_observability import ObservabilityPlugin, PluginConfig
from ai4icore_logging import (
    get_logger,
    CorrelationMiddleware,
    configure_logging,
)
from ai4icore_telemetry import setup_tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from ai4icore_model_management import ModelManagementPlugin, ModelManagementConfig, AuthContextMiddleware

load_dotenv()

from routers.health_router import health_router
from routers.inference_router import inference_router
from utils.service_registry_client import ServiceRegistryHttpClient
from middleware.error_handler_middleware import add_error_handlers
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.tenant_schema_router import TenantSchemaRouter
from middleware.tenant_middleware import TenantMiddleware

from models import database_models, auth_models

# Configure structured logging
# This also configures uvicorn loggers to use our formatter and disables access logs
# Set root_level=INFO to ensure successful 200 requests are logged to OpenSearch
configure_logging(
    service_name=os.getenv("SERVICE_NAME", "language-detection-service"),
    use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
    root_level=logging.INFO,  # Allow INFO level logs (including 200 status requests)
)

# Aggressively disable uvicorn access logger BEFORE uvicorn starts
# This must happen before uvicorn imports/creates its loggers
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

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT") or os.getenv("REDIS_PORT_NUMBER", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
REDIS_TIMEOUT = int(os.getenv("REDIS_TIMEOUT", "10"))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db"
)
# Multi-tenant database URL for tenant schema routing
MULTI_TENANT_DB_URL = os.getenv("MULTI_TENANT_DB_URL")
# NOTE: Triton endpoint/model MUST come from Model Management for inference.
# No environment variable fallback - all resolution via Model Management database.
TRITON_API_KEY = os.getenv("TRITON_API_KEY", "")

redis_client: Optional[redis.Redis] = None
db_engine: Optional[AsyncEngine] = None
db_session_factory: Optional[async_sessionmaker] = None
registry_client: Optional[ServiceRegistryHttpClient] = None
registered_instance_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, db_engine, db_session_factory, registry_client, registered_instance_id
    
    logger.info("Starting Language Detection Service...")
    
    # Redis connection
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to connect to Redis at {REDIS_HOST}:{REDIS_PORT} (attempt {attempt + 1}/{max_retries})...")
            redis_client = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
                decode_responses=True, socket_connect_timeout=REDIS_TIMEOUT,
                socket_timeout=REDIS_TIMEOUT, retry_on_timeout=True, health_check_interval=30,
            )
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
                retry_delay *= 2
            else:
                logger.warning("⚠ Redis connection failed after all retries")
                redis_client = None
    
    # PostgreSQL connection
    try:
        logger.info("Connecting to PostgreSQL...")
        db_engine = create_async_engine(
            DATABASE_URL, pool_size=20, max_overflow=10, pool_pre_ping=True,
            pool_recycle=3600, echo=False, connect_args={"timeout": 30, "command_timeout": 30},
        )
        db_session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        
        async with asyncio.timeout(60):
            async with db_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
        logger.info("✓ PostgreSQL connection established successfully")        
        # Create tables if they do not exist
        try:
            async with db_engine.begin() as conn:
                await conn.run_sync(database_models.Base.metadata.create_all)
            logger.info("✓ Database tables verified/created successfully")
        except Exception as e:
            logger.error(f"❌ Failed to create database tables: {e}")
            raise
    except Exception as e:
        logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
        raise
    
    app.state.redis_client = redis_client
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    # Triton endpoint/model resolved via Model Management middleware - no hardcoded fallback
    app.state.triton_api_key = TRITON_API_KEY

    # Initialize tenant schema router for multi-tenant routing
    if not MULTI_TENANT_DB_URL:
        logger.warning("MULTI_TENANT_DB_URL not configured. Tenant schema routing may not work correctly.")
        multi_tenant_db_url = DATABASE_URL
    else:
        multi_tenant_db_url = MULTI_TENANT_DB_URL
    logger.info("Using MULTI_TENANT_DB_URL: %s", (multi_tenant_db_url or "").split("@")[0] + "@***" if multi_tenant_db_url else "not set")
    tenant_schema_router = TenantSchemaRouter(database_url=multi_tenant_db_url)
    app.state.tenant_schema_router = tenant_schema_router
    logger.info("Tenant schema router initialized with multi-tenant database")

    # Service registry
    try:
        registry_client = ServiceRegistryHttpClient()
        service_name = os.getenv("SERVICE_NAME", "language-detection-service")
        service_port = int(os.getenv("SERVICE_PORT", "8090"))
        public_base_url = os.getenv("SERVICE_PUBLIC_URL")
        if public_base_url:
            service_url = public_base_url.rstrip("/")
        else:
            service_host = os.getenv("SERVICE_HOST", service_name)
            service_url = f"http://{service_host}:{service_port}"
        health_url = service_url + "/api/v1/language-detection/health"
        instance_id = os.getenv("SERVICE_INSTANCE_ID", f"{service_name}-{os.getpid()}")
        
        registered_instance_id = await registry_client.register(
            service_name=service_name,
            service_url=service_url,
            health_check_url=health_url,
            service_metadata={"instance_id": instance_id, "status": "healthy"},
        )
        if registered_instance_id:
            logger.info("Registered %s with service registry as instance %s", service_name, registered_instance_id)
    except Exception as e:
        logger.warning("Service registry registration error: %s", e)
    
    logger.info("✅ Language Detection Service started successfully")
    yield
    
    logger.info("Shutting down Language Detection Service...")
    try:
        if registry_client and registered_instance_id:
            service_name = os.getenv("SERVICE_NAME", "language-detection-service")
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
    logger.info("Language Detection Service shutdown complete")


app = FastAPI(
    title="Language Detection Service",
    version="1.0.0",
    description="Language detection microservice for identifying text language and script (IndicLID).",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Correlation middleware (MUST be before RequestLoggingMiddleware)
# This extracts X-Correlation-ID from headers and sets it in logging context
app.add_middleware(CorrelationMiddleware)

# Request logging (added BEFORE ObservabilityMiddleware)
# FastAPI middleware runs in REVERSE order, so this will run AFTER ObservabilityMiddleware
# This ensures organization is set in context before logging
app.add_middleware(RequestLoggingMiddleware)

# Observability (MUST be added AFTER RequestLoggingMiddleware)
# FastAPI middleware runs in REVERSE order, so this will run FIRST
# This ensures organization is extracted and set in context before RequestLoggingMiddleware logs
obs_config = PluginConfig.from_env()
obs_config.enabled = True  # Enable plugin
obs_config.debug = False  # Disable debug print statements - use structured logging instead
if not obs_config.customers:
    obs_config.customers = []  # Will be extracted from JWT/headers automatically
if not obs_config.apps:
    obs_config.apps = ["language-detection"]  # Service name

observability_plugin = ObservabilityPlugin(obs_config)
observability_plugin.register_plugin(app)
logger.info("✅ AI4ICore Observability Plugin initialized for Language Detection service")

# Model Management Plugin - single source of truth for Triton endpoint/model (no env fallback)
# MUST be registered BEFORE app starts (before other middleware) to avoid "Cannot add middleware after application has started" error
try:
    mm_config = ModelManagementConfig(
        model_management_service_url=os.getenv("MODEL_MANAGEMENT_SERVICE_URL", "http://model-management-service:8091"),
        model_management_api_key=os.getenv("MODEL_MANAGEMENT_SERVICE_API_KEY"),
        cache_ttl_seconds=300,
        triton_endpoint_cache_ttl=300,
        # Explicitly disable default Triton fallback – Model Management must resolve everything
        default_triton_endpoint="",
        default_triton_api_key="",
        middleware_enabled=True,
        middleware_paths=["/api/v1/language-detection"],
        request_timeout=10.0,
    )
    model_mgmt_plugin = ModelManagementPlugin(config=mm_config)
    model_mgmt_plugin.register_plugin(app, redis_client=None)
    app.add_middleware(AuthContextMiddleware, path_prefixes=mm_config.middleware_paths or ["/api/v1/language-detection"])
    logger.info("✅ Model Management Plugin initialized for Language Detection service")
except Exception as e:
    logger.warning(f"Failed to initialize Model Management Plugin: {e}")

# Add tenant middleware (after auth, before routes)
# This extracts tenant context from JWT or user_id
app.add_middleware(TenantMiddleware)

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
tracer = setup_tracing("language-detection-service")
if tracer:
    logger.info("✅ Distributed tracing initialized for Language Detection service")
    # Instrument FastAPI to automatically create spans for all requests
    # Exclude health check endpoints to reduce span noise
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="/health,/metrics,/enterprise/metrics,/docs,/redoc,/openapi.json"
    )
    logger.info("✅ FastAPI instrumentation enabled for tracing")
else:
    logger.warning("⚠️ Tracing not available (OpenTelemetry may not be installed)")

# Add rate limiting middleware (will use app.state.redis_client when available)
rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))
rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "2000"))
app.add_middleware(
    RateLimitMiddleware,
    redis_client=None,  # Will use app.state.redis_client as fallback
    requests_per_minute=rate_limit_per_minute,
    requests_per_hour=rate_limit_per_hour,
)

# Register error handlers
add_error_handlers(app)

# Routers
app.include_router(inference_router)
app.include_router(health_router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "language-detection-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Language detection microservice (IndicLID)",
        "redis_available": getattr(app.state, "redis_client", None) is not None,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)

