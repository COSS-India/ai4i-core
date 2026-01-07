"""
OCR Service - Optical Character Recognition microservice

Main FastAPI application entry point for the OCR microservice.
Provides batch OCR inference using Triton Inference Server (Surya OCR).
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

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

from ai4icore_observability import ObservabilityPlugin, PluginConfig
from ai4icore_logging import (
    get_logger,
    CorrelationMiddleware,
    configure_logging,
)
from ai4icore_telemetry import setup_tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from ai4icore_model_management import ModelManagementPlugin, ModelManagementConfig

from routers import inference_router
from utils.service_registry_client import ServiceRegistryHttpClient
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.error_handler_middleware import add_error_handlers
from models import database_models

# Configure structured logging
# This also configures uvicorn loggers to use our formatter and disables access logs
configure_logging(
    service_name=os.getenv("SERVICE_NAME", "ocr-service"),
    use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
)

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

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT") or os.getenv("REDIS_PORT_NUMBER", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
REDIS_TIMEOUT = int(os.getenv("REDIS_TIMEOUT", "10"))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db",
)


TRITON_API_KEY = os.getenv("TRITON_API_KEY", "")

redis_client: Optional[redis.Redis] = None
db_engine: Optional[AsyncEngine] = None
db_session_factory: Optional[async_sessionmaker] = None
registry_client: Optional[ServiceRegistryHttpClient] = None
registered_instance_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, db_engine, db_session_factory, registry_client, registered_instance_id

    # Disable uvicorn access logger AFTER uvicorn has started
    # This ensures it stays disabled even if uvicorn recreates loggers
    import logging
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True
    uvicorn_access.setLevel(logging.CRITICAL)  # Extra safety - set to highest level

    # Disable uvicorn access logger AFTER uvicorn has started
    # This ensures it stays disabled even if uvicorn recreates loggers
    import logging
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True
    uvicorn_access.setLevel(logging.CRITICAL)  # Extra safety - set to highest level
/////////////////////////////////////////////////////////////////////////
    logger.info("Starting OCR Service...")

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
        
        # NOTE: Tables should already exist in the database (created by migration scripts)
        # We don't create tables here - just verify connection works
    except Exception as e:
        logger.error("Failed to connect to PostgreSQL: %s", e)
        raise

    app.state.redis_client = redis_client
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    # Triton endpoint/model resolved via Model Management middleware - no hardcoded fallback
    app.state.triton_api_key = TRITON_API_KEY

    # Service registry
    try:
        registry_client = ServiceRegistryHttpClient()
        service_name = os.getenv("SERVICE_NAME", "ocr-service")
        service_port = int(os.getenv("SERVICE_PORT", "8090"))
        public_base_url = os.getenv("SERVICE_PUBLIC_URL")
        if public_base_url:
            service_url = public_base_url.rstrip("/")
        else:
            service_host = os.getenv("SERVICE_HOST", service_name)
            service_url = f"http://{service_host}:{service_port}"
        health_url = service_url + "/health"
        instance_id = os.getenv("SERVICE_INSTANCE_ID", f"{service_name}-{os.getpid()}")
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

    logger.info("OCR Service started successfully")

    yield

    logger.info("Shutting down OCR Service...")
    try:
        try:
            if registry_client and registered_instance_id:
                service_name = os.getenv("SERVICE_NAME", "ocr-service")
                await registry_client.deregister(service_name, registered_instance_id)
        except Exception as e:
            logger.warning("Service registry deregistration error: %s", e)

        if redis_client:
            await redis_client.close()
            logger.info("Redis connection closed")

        if db_engine:
            await db_engine.dispose()
            logger.info("PostgreSQL connection closed")
    except Exception as e:
        logger.error("Error during shutdown: %s", e)


app = FastAPI(
    title="OCR Service",
    version="1.0.0",
    description=(
        "Optical Character Recognition microservice using Surya OCR via "
        "Triton Inference Server. Extracts text from images in ULCA-style requests."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "OCR Inference", "description": "OCR inference endpoints"},
        {"name": "Health", "description": "Service health and readiness checks"},
    ],
    contact={
        "name": "AI4ICore Team",
        "url": "https://github.com/AI4X",
        "email": "support@ai4x.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
)

# Initialize AI4ICore Observability Plugin
# Plugin automatically extracts metrics from request bodies - no manual recording needed!
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
config = PluginConfig.from_env()
config.enabled = True  # Enable plugin
config.enabled = True
config.debug = True  # Enable debug logging for organization extraction
if not config.customers:
    config.customers = []  # Will be extracted from JWT/headers automatically
if not config.apps:
    config.apps = ["ocr"]  # Service name

plugin = ObservabilityPlugin(config)
plugin.register_plugin(app)
logger.info("✅ AI4ICore Observability Plugin initialized for OCR service")

# Model Management Plugin - registered AFTER Observability
# so that Model Management runs first and Observability can use cached body
try:
    from ai4icore_model_management import ModelManagementConfig
    mm_config = ModelManagementConfig(
        model_management_service_url=os.getenv("MODEL_MANAGEMENT_SERVICE_URL", "http://model-management-service:8091"),
        model_management_api_key=None,
        cache_ttl_seconds=300,
        triton_endpoint_cache_ttl=300,
        # Explicitly disable default Triton fallback – Model Management must resolve everything
        default_triton_endpoint="",
        default_triton_api_key="",
        middleware_enabled=True,
        middleware_paths=["/api/v1/ocr"],
        request_timeout=10.0,
    )
    model_mgmt_plugin = ModelManagementPlugin(config=mm_config)
    model_mgmt_plugin.register_plugin(app, redis_client=redis_client)
    logger.info("✅ Model Management Plugin initialized for OCR service")
except Exception as e:
    logger.warning(f"Failed to initialize Model Management Plugin: {e}")

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
tracer = setup_tracing("ocr-service")
if tracer:
    logger.info("✅ Distributed tracing initialized for OCR service")
    # Instrument FastAPI to automatically create spans for all requests
    FastAPIInstrumentor.instrument_app(app)
    logger.info("✅ FastAPI instrumentation enabled for tracing")
else:
    logger.warning("⚠️ Tracing not available (OpenTelemetry may not be installed)")

# Observability (MUST be added AFTER RequestLoggingMiddleware)
# FastAPI middleware runs in REVERSE order, so this will run FIRST
# This ensures organization is extracted and set in context before RequestLoggingMiddleware logs
config = PluginConfig.from_env()
config.enabled = True
config.debug = False  # Disable debug print statements - use structured logging instead
if not config.customers:
    config.customers = []
if not config.apps:
    config.apps = ["ocr"]



plugin = ObservabilityPlugin(config)

plugin.register_plugin(app)
logger.info("AI4ICore Observability Plugin initialized for OCR service")

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
tracer = setup_tracing("ocr-service")
if tracer:
    logger.info("✅ Distributed tracing initialized for OCR service")
    # Instrument FastAPI to automatically create spans for all requests
    FastAPIInstrumentor.instrument_app(app)
    logger.info("✅ FastAPI instrumentation enabled for tracing")
else:
    logger.warning("⚠️ Tracing not available (OpenTelemetry may not be installed)")

# Rate limiting (Redis client will be picked from app.state)
rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
app.add_middleware(
    RateLimitMiddleware,
    redis_client=None,
    requests_per_minute=rate_limit_per_minute,
    requests_per_hour=rate_limit_per_hour,
)

# Error handlers
add_error_handlers(app)

# Routers
app.include_router(inference_router.inference_router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "ocr-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Optical Character Recognition microservice",
    }


@app.get("/health", tags=["Health"])
async def health(request: Request):
    redis_ok = False
    db_ok = False

    try:
        rc = getattr(request.app.state, "redis_client", None)
        if rc is not None:
            await rc.ping()
            redis_ok = True
    except Exception as e:
        logger.warning("/health: Redis check failed: %s", e)

    try:
        session_factory = getattr(request.app.state, "db_session_factory", None)
        if session_factory is not None:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.warning("/health: PostgreSQL check failed: %s", e)

    status_str = "ok" if (redis_ok and db_ok) else "degraded"
    status_code = 200 if status_str == "ok" else 503

    return {
        "service": "ocr-service",
        "status": status_str,
        "redis_ok": redis_ok,
        "db_ok": db_ok,
        "version": "1.0.0",
    }, status_code


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("SERVICE_PORT", "8099"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=log_level,
        reload=False,
    )


