"""
ASR Service - Automatic Speech Recognition Microservice

Main FastAPI application entry point for the ASR microservice.
Provides batch ASR inference using Triton Inference Server.
"""

import asyncio
import importlib.util
import logging
import os
import traceback
from contextlib import asynccontextmanager
from typing import Dict, Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from ai4icore_observability import ObservabilityPlugin, PluginConfig
from ai4icore_logging import (
    get_logger,
    CorrelationMiddleware,
    configure_logging,
)
from ai4icore_telemetry import setup_tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from ai4icore_model_management import ModelManagementPlugin, ModelManagementConfig, AuthContextMiddleware

# Import streaming service components
from services.streaming_service import StreamingASRService
from services.audio_service import AudioService
from utils.triton_client import TritonClient
from repositories.asr_repository import ASRRepository

# Import middleware components
from middleware.auth_provider import AuthProvider
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.tenant_schema_router import TenantSchemaRouter
from middleware.tenant_middleware import TenantMiddleware
from middleware.error_handler_middleware import add_error_handlers
from middleware.exceptions import AuthenticationError, AuthorizationError, RateLimitExceededError
from utils.service_registry_client import ServiceRegistryHttpClient

# Configure structured logging (to OpenSearch, with correlation IDs)
configure_logging(
    service_name=os.getenv("SERVICE_NAME", "asr-service"),
    use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
)

# Aggressively disable uvicorn access logger BEFORE uvicorn starts
# This must happen before uvicorn imports/creates its loggers

uvicorn_access = logging.getLogger("uvicorn.access")
uvicorn_access.handlers.clear()
uvicorn_access.propagate = False
uvicorn_access.disabled = True
uvicorn_access.setLevel(logging.CRITICAL + 1)

# Get logger instance
logger = get_logger(__name__)

# Global variables for database and Redis connections
redis_client: redis.Redis = None
db_engine = None
db_session_factory = None
streaming_service: StreamingASRService = None
registry_client: ServiceRegistryHttpClient = None
registered_instance_id: str = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting ASR Service...")
    
    try:
        # Use the already initialized Redis client
        global redis_client
        if redis_client is None:
            # Fallback Redis initialization if not done earlier
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT_NUMBER", "6379"))
            redis_password = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
            
            redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}"
            redis_client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
            
            # Test Redis connection
            await redis_client.ping()
            logger.info("Redis connection established successfully")
        else:
            logger.info("Using existing Redis connection")
        
        # Initialize PostgreSQL async engine
        global db_engine, db_session_factory
        database_url = os.getenv(
            "DATABASE_URL", 
            "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db"
        )
        
        db_pool_size = int(os.getenv("DB_POOL_SIZE", "20"))
        db_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
        
        db_engine = create_async_engine(
            database_url,
            pool_size=db_pool_size,
            max_overflow=db_max_overflow,
            echo=False
        )
        
        # Create async session factory
        db_session_factory = async_sessionmaker(
            db_engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
        
        # Test database connection
        async with db_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection established successfully")
        
        # NOTE: Triton endpoint/model MUST come from Model Management for inference.
        # No environment variable fallback - all resolution via Model Management database.
        TRITON_API_KEY = os.getenv("TRITON_API_KEY", "")
        TRITON_TIMEOUT = float(os.getenv("TRITON_TIMEOUT", "300.0"))
        
        # Store Triton config in app state (for use by routers after Model Management resolution)
        app.state.triton_api_key = TRITON_API_KEY
        app.state.triton_timeout = TRITON_TIMEOUT


        # Initialize tenant schema router for multi-tenant routing
        multi_tenant_db_url = os.getenv("MULTI_TENANT_DB_URL")
        if not multi_tenant_db_url:
            logger.warning("MULTI_TENANT_DB_URL not configured. Tenant schema routing may not work correctly.")
            multi_tenant_db_url = database_url
        logger.info(f"Using MULTI_TENANT_DB_URL: {multi_tenant_db_url.split('@')[0]}@***")
        tenant_schema_router = TenantSchemaRouter(database_url=multi_tenant_db_url)
        app.state.tenant_schema_router = tenant_schema_router
        logger.info("Tenant schema router initialized with multi-tenant database")
        
        # Initialize streaming service (optional - requires Model Management serviceId)
        global streaming_service
        try:
            # Create dependencies
            audio_service = AudioService()
            # NOTE: Streaming service Triton client will be created per-request via Model Management
            # For now, skip Triton client initialization here
            triton_client = None
            
            # Create async session for repository
            async with db_session_factory() as session:
                repository = ASRRepository(session)
                
                # Create streaming service
                # NOTE: Streaming service requires Model Management for Triton client resolution
                # For now, skip streaming service initialization if Triton client is not available
                if triton_client:
                    response_frequency_ms = int(os.getenv("STREAMING_RESPONSE_FREQUENCY_MS", "2000"))
                    streaming_service = StreamingASRService(
                        audio_service=audio_service,
                        triton_client=triton_client,
                        repository=repository,
                        redis_client=redis_client,
                        response_frequency_in_ms=response_frequency_ms
                    )
                else:
                    logger.warning("Streaming service skipped - requires Model Management for Triton resolution")
                
                # Mount Socket.IO streaming endpoint only if streaming service was initialized
                if streaming_service:
                    app.mount("/socket.io", streaming_service.app)
                    logger.info("Socket.IO streaming endpoint mounted at /socket.io")
                    logger.info("Streaming service initialized successfully")
                else:
                    logger.info("Streaming service initialization skipped - not available")
        except Exception as e:
            logger.error(f"Failed to initialize streaming service: {e}")
            # Continue without streaming (optional feature)
        
        # Store connections in app state for middleware access
        app.state.redis_client = redis_client
        app.state.db_engine = db_engine
        app.state.db_session_factory = db_session_factory
        
        # NOTE: Triton endpoint/model MUST come from Model Management for inference.
        # No environment variable fallback - all resolution via Model Management database.
        TRITON_API_KEY = os.getenv("TRITON_API_KEY", "")
        TRITON_TIMEOUT = float(os.getenv("TRITON_TIMEOUT", "300.0"))
        
        # Store Triton config in app state (for use by routers after Model Management resolution)
        app.state.triton_api_key = TRITON_API_KEY
        app.state.triton_timeout = TRITON_TIMEOUT
        
        # NOTE: Error handlers are registered AFTER app starts (outside lifespan)
        # to match NMT/TTS pattern and ensure proper registration order
        # to ensure middleware can be added. See line ~330 for registration.
        
        # Register service in central registry via config-service
        try:
            global registry_client, registered_instance_id
            registry_client = ServiceRegistryHttpClient()
            service_name = os.getenv("SERVICE_NAME", "asr-service")
            service_port = int(os.getenv("SERVICE_PORT", "8087"))
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

        logger.info("ASR Service started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start ASR Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down ASR Service...")
    
    try:
        # Deregister from registry if previously registered
        try:
            if registry_client and registered_instance_id:
                service_name = os.getenv("SERVICE_NAME", "asr-service")
                await registry_client.deregister(service_name, registered_instance_id)
        except Exception as e:
            logger.warning("Service registry deregistration error: %s", e)

        # Close Redis client
        if redis_client:
            await redis_client.close()
            logger.info("Redis connection closed")
        
        # Dispose database engine
        if db_engine:
            await db_engine.dispose()
            logger.info("PostgreSQL connection closed")
        
        logger.info("ASR Service shutdown complete")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Create FastAPI application
app = FastAPI(
    title="ASR Service",
    version="1.0.0",
    description="Automatic Speech Recognition microservice for converting speech to text. Supports 22+ Indic languages with real-time streaming and batch processing.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "ASR Inference",
            "description": "Speech-to-text conversion endpoints"
        },
        {
            "name": "Health",
            "description": "Service health and readiness checks"
        },
        {
            "name": "Models",
            "description": "ASR model management"
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
    
# Initialize AI4ICore Observability Plugin
# Plugin automatically extracts metrics from request bodies - no manual recording needed!
config = PluginConfig.from_env()
config.enabled = True  # Enable plugin
if not config.customers:
    config.customers = []  # Will be extracted from JWT/headers automatically
if not config.apps:
    config.apps = ["asr"]  # Service name

plugin = ObservabilityPlugin(config)
plugin.register_plugin(app)
logger.info("✅ AI4ICore Observability Plugin initialized for ASR service")

# Model Management Plugin - registered AFTER Observability
# so that Model Management runs first and Observability can use cached body
TRITON_API_KEY = os.getenv("TRITON_API_KEY", "")
model_mgmt_config = ModelManagementConfig(
    model_management_service_url=os.getenv("MODEL_MANAGEMENT_SERVICE_URL", "http://model-management-service:8091"),
    model_management_api_key=os.getenv("MODEL_MANAGEMENT_SERVICE_API_KEY"),
    cache_ttl_seconds=300,
    triton_endpoint_cache_ttl=300,
    default_triton_endpoint="",  # No fallback - must come from Model Management
    default_triton_api_key=TRITON_API_KEY,
    middleware_enabled=True,
    middleware_paths=["/api/v1"]
)
model_mgmt_plugin = ModelManagementPlugin(model_mgmt_config)
model_mgmt_plugin.register_plugin(app, redis_client=redis_client)
app.add_middleware(AuthContextMiddleware, path_prefixes=model_mgmt_config.middleware_paths or ["/api/v1"])
logger.info("✅ Model Management Plugin initialized for ASR service")

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
tracer = setup_tracing("asr-service")
if tracer:
    logger.info("✅ Distributed tracing initialized for ASR service")
    # Instrument FastAPI to automatically create spans for all requests
    FastAPIInstrumentor.instrument_app(app)
    logger.info("✅ FastAPI instrumentation enabled for tracing")
else:
    logger.warning("⚠️ Tracing not available (OpenTelemetry may not be installed)")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Redis client early for middleware
redis_client = None
try:
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT_NUMBER", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
    
    redis_client = redis.Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True
    )
    
    # Test Redis connection - skip ping test here (async Redis requires await)
    # Connection will be properly tested in lifespan function
    logger.info("Redis client created for middleware (connection will be tested in lifespan)")
except Exception as e:
    logger.warning(f"Redis connection failed for middleware: {e}")
    redis_client = None

# NOTE: Model Management Plugin is now registered BEFORE Observability (above)
# so that Observability runs first and caches the body, then Model Management can use cached body

# Add middleware after FastAPI app creation
# Tenant middleware (MUST be early to mark tenant-aware routes)
app.add_middleware(TenantMiddleware)
# Correlation middleware (MUST be before RequestLoggingMiddleware)
app.add_middleware(CorrelationMiddleware)
# Structured request logging middleware (logs to OpenSearch)
app.add_middleware(RequestLoggingMiddleware)

# Add rate limiting middleware (if Redis is available)
if redis_client:
    rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
    app.add_middleware(
        RateLimitMiddleware,
        redis_client=redis_client,
        requests_per_minute=rate_limit_per_minute,
        requests_per_hour=rate_limit_per_hour
    )
    logger.info("Rate limiting middleware added")
else:
    logger.warning("Rate limiting middleware skipped - Redis not available")

# Mount Socket.IO streaming endpoint will be done in lifespan function


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint returning service information."""
    return {
        "name": "ASR Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Automatic Speech Recognition service"
    }


@app.get("/streaming/info")
async def streaming_info() -> Dict[str, Any]:
    """Get streaming endpoint information."""
    if not streaming_service:
        from middleware.exceptions import ErrorDetail
        from services.constants.error_messages import SERVICE_UNAVAILABLE, SERVICE_UNAVAILABLE_MESSAGE
        import time
        error_detail = ErrorDetail(
            message=SERVICE_UNAVAILABLE_MESSAGE,
            code=SERVICE_UNAVAILABLE
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail.dict()
        )
    
    return {
        "endpoint": "/socket.io/asr",
        "protocol": "Socket.IO",
        "events": {
            "client_to_server": ["start", "data", "disconnect"],
            "server_to_client": ["ready", "response", "error", "terminate"]
        },
        "connection_params": {
            "serviceId": "ASR model identifier (required)",
            "language": "Language code (required)",
            "samplingRate": "Audio sample rate in Hz (required)",
            "apiKey": "API key for authentication (optional)",
            "preProcessors": "JSON array of preprocessors (optional)",
            "postProcessors": "JSON array of postprocessors (optional)"
        },
        "example_url": "ws://localhost:8087/socket.io/asr?serviceId=vakyansh-asr-en&language=en&samplingRate=16000"
    }


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for service and dependencies."""
    health_status = {
        "status": "healthy",
        "service": "asr-service",
        "version": "1.0.0",
        "redis": "unhealthy",
        "postgres": "unhealthy",
        "triton": "unhealthy",
        "timestamp": None
    }
    
    # Check if health logs should be excluded
    exclude_health_logs = os.getenv("EXCLUDE_HEALTH_LOGS", "false").lower() == "true"
    
    try:
        import time
        health_status["timestamp"] = time.time()
        
        # Check Redis connectivity
        if redis_client:
            await redis_client.ping()
            health_status["redis"] = "healthy"
        else:
            health_status["redis"] = "unavailable"
            
    except Exception as e:
        if not exclude_health_logs:
            logger.error(f"Redis health check failed: {e}")
        health_status["redis"] = "unhealthy"
    
    try:
        # Check PostgreSQL connectivity
        if db_engine:
            async with db_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            health_status["postgres"] = "healthy"
        else:
            health_status["postgres"] = "unavailable"
            
    except Exception as e:
        if not exclude_health_logs:
            logger.error(f"PostgreSQL health check failed: {e}")
        health_status["postgres"] = "unhealthy"
    
    try:
        # Triton endpoint must be resolved via Model Management - no hardcoded fallback
        # Skip Triton check in health endpoint (requires Model Management serviceId)
        if not exclude_health_logs:
            logger.debug("/health: Skipping Triton check (requires Model Management serviceId)")
        health_status["triton"] = "unknown"
    except Exception as e:
        if not exclude_health_logs:
            logger.warning(f"Triton health check skipped: {e}")
        health_status["triton"] = "unknown"
    
    # Determine overall status (Triton check skipped, only Redis and DB matter)
    if (health_status["redis"] == "healthy" and 
        health_status["postgres"] == "healthy"):
        health_status["status"] = "healthy"
    else:
        health_status["status"] = "unhealthy"
    
    return health_status


# Include routers
try:
    # Use importlib to explicitly load routers from the service root to avoid conflicts
    _service_root = os.path.dirname(os.path.abspath(__file__))
    _inference_router_path = os.path.join(_service_root, 'routers', 'inference_router.py')
    _health_router_path = os.path.join(_service_root, 'routers', 'health_router.py')
    
    # Load inference_router
    spec = importlib.util.spec_from_file_location("inference_router", _inference_router_path)
    inference_router_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inference_router_module)
    inference_router = inference_router_module.inference_router
    
    # Load health_router
    spec = importlib.util.spec_from_file_location("health_router", _health_router_path)
    health_router_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(health_router_module)
    health_router = health_router_module.health_router
    
    # Register error handlers (AFTER middleware, BEFORE routes - matches NMT/TTS pattern)
    add_error_handlers(app)
    
    app.include_router(inference_router)
    app.include_router(health_router)
    logger.info("✅ Routers registered successfully")
    
except ImportError as e:
    error_details = traceback.format_exc()
    logger.error(f"Could not import routers: {e}")
    logger.error(f"Import error details:\n{error_details}")
    logger.warning("Service will start without API endpoints.")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("SERVICE_PORT", "8087"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=log_level,
        reload=False  # Enable auto-reload for development
    )