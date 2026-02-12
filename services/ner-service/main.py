"""
NER Service - Named Entity Recognition microservice

Main FastAPI application entry point for the NER microservice.
Provides batch NER inference using Triton Inference Server.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as redis
import redis as redis_sync  # For synchronous Redis client for middleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Observability imports (optional)
OBSERVABILITY_AVAILABLE = False
ObservabilityPlugin = None
PluginConfig = None
try:
    from ai4icore_observability import ObservabilityPlugin, PluginConfig
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    pass

# Model Management imports (required)
from ai4icore_model_management import ModelManagementPlugin, ModelManagementConfig

# Telemetry imports (optional)
TELEMETRY_AVAILABLE = False
setup_tracing = None
FastAPIInstrumentor = None
try:
    from ai4icore_telemetry import setup_tracing
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    TELEMETRY_AVAILABLE = True
except ImportError:
    pass  # Will be handled below

# Logging imports
LOGGING_AVAILABLE = False
configure_logging = None
get_logger = None
CorrelationMiddleware = None
try:
    from ai4icore_logging import configure_logging, get_logger, CorrelationMiddleware
    LOGGING_AVAILABLE = True
except ImportError:
    pass

from routers import inference_router
from utils.service_registry_client import ServiceRegistryHttpClient
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.error_handler_middleware import add_error_handlers
from middleware.tenant_middleware import TenantMiddleware
from middleware.tenant_schema_router import TenantSchemaRouter
from models import database_models
from models import auth_models  # Import to ensure auth tables are created

# Configure structured logging (to OpenSearch, with correlation IDs)
if LOGGING_AVAILABLE:
    configure_logging(
        service_name=os.getenv("SERVICE_NAME", "ner-service"),
        use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
    )
    logger = get_logger(__name__)
    
    # Aggressively disable uvicorn access logger BEFORE uvicorn starts
    # This must happen before uvicorn imports/creates its loggers
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True
    uvicorn_access.setLevel(logging.CRITICAL + 1)  # Set above CRITICAL to ensure nothing logs
else:
    # Fallback to standard logging if ai4icore_logging is not available
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT") or os.getenv("REDIS_PORT_NUMBER", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
REDIS_TIMEOUT = int(os.getenv("REDIS_TIMEOUT", "10"))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db",
)

# Multi-tenant database URL (for tenant schema routing)
MULTI_TENANT_DB_URL = os.getenv(
    "MULTI_TENANT_DB_URL",
    "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/multi_tenant_db",
)

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

    logger.info("Starting NER Service...")

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
            # Use asyncio.wait_for for Python 3.10 compatibility
            async def test_connection():
                async with db_engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
            await asyncio.wait_for(test_connection(), timeout=60.0)
        except asyncio.TimeoutError:
            raise Exception("PostgreSQL connection timeout after 60 seconds")

        logger.info("PostgreSQL connection established successfully")

        # Create tables if they do not exist
        try:
            async with db_engine.begin() as conn:
                await conn.run_sync(database_models.Base.metadata.create_all)
            logger.info("NER database tables verified/created successfully")
        except Exception as e:
            logger.error("Failed to create NER database tables: %s", e)
            raise
    except Exception as e:
        logger.error("Failed to connect to PostgreSQL: %s", e)
        raise

    app.state.redis_client = redis_client
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    # Triton endpoint/model resolved via Model Management middleware - no hardcoded fallback
    app.state.triton_api_key = TRITON_API_KEY

    # Initialize tenant schema router for multi-tenant routing
    # Use MULTI_TENANT_DB_URL for tenant schema routing (different from auth DATABASE_URL)
    if not MULTI_TENANT_DB_URL:
        logger.warning("MULTI_TENANT_DB_URL not configured. Tenant schema routing may not work correctly.")
        multi_tenant_db_url = DATABASE_URL
    else:
        multi_tenant_db_url = MULTI_TENANT_DB_URL

    logger.info(f"Using MULTI_TENANT_DB_URL: {multi_tenant_db_url.split('@')[0]}@***")  # Mask password in logs
    tenant_schema_router = TenantSchemaRouter(database_url=multi_tenant_db_url)
    app.state.tenant_schema_router = tenant_schema_router
    logger.info("Tenant schema router initialized with multi-tenant database")

    # Service registry
    try:
        registry_client = ServiceRegistryHttpClient()
        service_name = os.getenv("SERVICE_NAME", "ner-service")
        service_port = int(os.getenv("SERVICE_PORT", "8091"))
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

    logger.info("NER Service started successfully")

    yield

    logger.info("Shutting down NER Service...")
    try:
        try:
            if registry_client and registered_instance_id:
                service_name = os.getenv("SERVICE_NAME", "ner-service")
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
        if hasattr(app.state, 'tenant_schema_router') and app.state.tenant_schema_router:
            await app.state.tenant_schema_router.close_all()
            logger.info("Tenant schema router connections closed")
    except Exception as e:
        logger.error("Error during shutdown: %s", e)


app = FastAPI(
    title="NER Service",
    version="1.0.0",
    description=(
        "Named Entity Recognition microservice using Dhruva NER via "
        "Triton Inference Server. Extracts entities from text in ULCA-style requests."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "NER Inference", "description": "NER inference endpoints"},
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

# Observability (optional)
if OBSERVABILITY_AVAILABLE and ObservabilityPlugin:
    try:
        config = PluginConfig.from_env()
        config.enabled = True
        if not config.customers:
            config.customers = []
        if not config.apps:
            config.apps = ["ner"]

        observability_plugin = ObservabilityPlugin(config)
        observability_plugin.register_plugin(app)
        logger.info("AI4ICore Observability Plugin initialized for NER service")
    except Exception as e:
        logger.warning(f"Failed to initialize Observability Plugin: {e}")

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
if TELEMETRY_AVAILABLE and setup_tracing:
    try:
        tracer = setup_tracing("ner-service")
        if tracer:
            logger.info("✅ Distributed tracing initialized for NER service")
            # Instrument FastAPI to automatically create spans for all requests
            # Exclude health check endpoints to reduce span noise
            if FastAPIInstrumentor:
                FastAPIInstrumentor.instrument_app(
                    app,
                    excluded_urls="/health,/metrics,/enterprise/metrics,/docs,/redoc,/openapi.json"
                )
                logger.info("✅ FastAPI instrumentation enabled for tracing")
        else:
            logger.warning("⚠️ Tracing setup returned None - traces may not be exported to Jaeger")
    except Exception as e:
        logger.warning(f"⚠️ Failed to setup tracing: {e}")
        logger.warning("⚠️ Traces will not be exported to Jaeger - check OpenTelemetry installation and Jaeger endpoint")
else:
    logger.warning("⚠️ Tracing not available (OpenTelemetry may not be installed)")

# Initialize Redis client early for middleware (synchronous for Model Management Plugin)
redis_client_sync = None
try:
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT") or os.getenv("REDIS_PORT_NUMBER", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
    
    redis_client_sync = redis_sync.Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
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
try:
    mm_config = ModelManagementConfig(
        model_management_service_url=os.getenv("MODEL_MANAGEMENT_SERVICE_URL", "http://model-management-service:8091"),
        model_management_api_key=os.getenv("MODEL_MANAGEMENT_SERVICE_API_KEY"),
        cache_ttl_seconds=300,
        triton_endpoint_cache_ttl=300,
        # Explicitly disable default Triton fallback – Model Management must resolve everything
        default_triton_endpoint="",
        default_triton_api_key=TRITON_API_KEY,
        middleware_enabled=True,
        middleware_paths=["/api/v1/ner"],
        request_timeout=10.0,
    )
    model_mgmt_plugin = ModelManagementPlugin(config=mm_config)
    model_mgmt_plugin.register_plugin(app, redis_client=redis_client_sync)
    logger.info("✅ Model Management Plugin initialized for NER service")
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

# Correlation middleware (MUST be before RequestLoggingMiddleware)
# This extracts X-Correlation-ID from headers and sets it in logging context
if CorrelationMiddleware:
    app.add_middleware(CorrelationMiddleware)

# Request logging
app.add_middleware(RequestLoggingMiddleware)

# Tenant middleware (marks NER requests for tenant context extraction)
app.add_middleware(TenantMiddleware)

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
app.include_router(inference_router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "ner-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Named Entity Recognition microservice",
    }


@app.get("/health", tags=["Health"])
async def health(request: Request):
    redis_ok = False
    db_ok = False

    # Check if health logs should be excluded
    exclude_health_logs = os.getenv("EXCLUDE_HEALTH_LOGS", "false").lower() == "true"

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

    status_str = "ok" if (redis_ok and db_ok) else "degraded"
    status_code = 200 if status_str == "ok" else 503

    return {
        "service": "ner-service",
        "status": status_str,
        "redis_ok": redis_ok,
        "db_ok": db_ok,
        "version": "1.0.0",
    }, status_code


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("SERVICE_PORT", "9001"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=log_level,
        reload=False,
    )



