"""
LLM Service - Large Language Model microservice
Main FastAPI application entry point
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

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
from ai4icore_model_management import ModelManagementPlugin, ModelManagementConfig

from routers.health_router import health_router
from routers.inference_router import inference_router
from utils.triton_client import TritonClient
from utils.service_registry_client import ServiceRegistryHttpClient
from middleware.auth_provider import AuthProvider
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.error_handler_middleware import add_error_handlers
from middleware.exceptions import AuthenticationError, AuthorizationError, RateLimitExceededError

# Import models to ensure they are registered with SQLAlchemy
from models import database_models, auth_models

# Configure structured logging
# This also configures uvicorn loggers to use our formatter and disables access logs
# Set root_level=INFO to ensure successful 200 requests are logged to OpenSearch
configure_logging(
    service_name=os.getenv("SERVICE_NAME", "llm-service"),
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

# Environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db")
TRITON_ENDPOINT = os.getenv("TRITON_ENDPOINT", "http://13.220.11.146:8000")
TRITON_API_KEY = os.getenv("TRITON_API_KEY", "")
TRITON_TIMEOUT = float(os.getenv("TRITON_TIMEOUT", "300.0"))

# Global variables
redis_client: Optional[redis.Redis] = None
db_engine: Optional[AsyncEngine] = None
db_session_factory: Optional[async_sessionmaker] = None
registry_client: Optional[ServiceRegistryHttpClient] = None
registered_instance_id: Optional[str] = None

# Initialize Redis client early for middleware
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True
    )
    
    # Test Redis connection
    asyncio.run(redis_client.ping())
    logger.info("Redis connection established for middleware")
except Exception as e:
    logger.warning(f"Redis connection failed for middleware: {e}")
    redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown"""
    global redis_client, db_engine, db_session_factory, registry_client, registered_instance_id
    
    # Startup
    logger.info("Starting LLM Service...")
    
    try:
        # Use existing Redis client or initialize if needed
        global redis_client
        if redis_client is None:
            logger.info("Connecting to Redis...")
            redis_client = redis.from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}",
                password=REDIS_PASSWORD,
                decode_responses=True
            )
            await redis_client.ping()
            logger.info("Redis connection established")
        else:
            logger.info("Using existing Redis connection")
        
        # Initialize PostgreSQL
        logger.info("Connecting to PostgreSQL...")
        db_engine = create_async_engine(
            DATABASE_URL,
            pool_size=20,
            max_overflow=10,
            echo=False
        )
        db_session_factory = async_sessionmaker(
            db_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Test database connection
        async with db_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection established")
        
        # Store in app state for middleware access
        app.state.redis_client = redis_client
        app.state.db_engine = db_engine
        app.state.db_session_factory = db_session_factory
        app.state.triton_endpoint = TRITON_ENDPOINT
        app.state.triton_api_key = TRITON_API_KEY
        app.state.triton_timeout = TRITON_TIMEOUT
        
        # Register service into the central registry via config-service
        try:
            registry_client = ServiceRegistryHttpClient()
            service_name = os.getenv("SERVICE_NAME", "llm-service")
            service_port = int(os.getenv("SERVICE_PORT", "8090"))
            # Prefer explicit public base URL if provided
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
                logger.info("Registered %s with service registry as instance %s", service_name, registered_instance_id)
            else:
                logger.warning("Service registry registration skipped/failed for %s", service_name)
        except Exception as e:
            logger.warning("Service registry registration error: %s", e)
        
        logger.info("LLM Service started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start LLM Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down LLM Service...")
    
    try:
        # Deregister from registry if previously registered
        try:
            if registry_client and registered_instance_id:
                service_name = os.getenv("SERVICE_NAME", "llm-service")
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
        logger.error(f"Error during shutdown: {e}")
    
    logger.info("LLM Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="LLM Service",
    version="1.0.0",
    description="Large Language Model microservice for text processing, translation, and generation. Supports multiple Indic Languages.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "LLM Inference",
            "description": "Large language model inference endpoints"
        },
        {
            "name": "Models",
            "description": "LLM model management"
        },
        {
            "name": "Health",
            "description": "Service health and readiness checks"
        }
    ],
    contact={
        "name": "Dhruva Platform Team",
        "url": "https://github.com/AI4Bharat/Dhruva",
        "email": "support@dhruva-platform.com"
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT"
    },
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
    obs_config.apps = ["llm"]  # Service name

observability_plugin = ObservabilityPlugin(obs_config)
observability_plugin.register_plugin(app)
logger.info("✅ AI4ICore Observability Plugin initialized for LLM service")

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
        middleware_paths=["/api/v1/llm"],
        request_timeout=10.0,
    )
    model_mgmt_plugin = ModelManagementPlugin(config=mm_config)
    model_mgmt_plugin.register_plugin(app, redis_client=None)
    logger.info("✅ Model Management Plugin initialized for LLM service")
except Exception as e:
    logger.warning(f"Failed to initialize Model Management Plugin: {e}")

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
tracer = setup_tracing("llm-service")
if tracer:
    logger.info("✅ Distributed tracing initialized for LLM service")
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
rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
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
app.include_router(health_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "llm-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Large Language Model microservice"
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)

