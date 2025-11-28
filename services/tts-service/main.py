"""
TTS Service - Text-to-Speech Microservice

Main FastAPI application entry point for the TTS microservice.
Provides batch TTS inference using Triton Inference Server.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Import service components
from services.tts_service import TTSService
from services.audio_service import AudioService
from services.text_service import TextService
from services.voice_service import VoiceService
from utils.triton_client import TritonClient
from repositories.tts_repository import TTSRepository

# Try to import streaming service, but make it optional
try:
    from services.streaming_service import StreamingTTSService
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    StreamingTTSService = None

# Import middleware components
from middleware.auth_provider import AuthProvider
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.error_handler_middleware import add_error_handlers
from middleware.exceptions import AuthenticationError, AuthorizationError, RateLimitExceededError
from utils.service_registry_client import ServiceRegistryHttpClient

# Observability integration - Dhruva Observability Plugin
from dhruva_observability import ObservabilityPlugin, PluginConfig

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global variables for database and Redis connections
redis_client: redis.Redis = None
db_engine = None
db_session_factory = None
streaming_service: StreamingTTSService = None
registry_client: ServiceRegistryHttpClient = None
registered_instance_id: str = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting TTS Service...")
    
    try:
        # Initialize Redis connection
        global redis_client
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT_NUMBER", "6379"))
        redis_password = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
        
        redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}"
        redis_client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        
        # Test Redis connection
        await redis_client.ping()
        logger.info("Redis connection established successfully")
        
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
        
        # Store connections in app state for middleware access
        app.state.redis_client = redis_client
        app.state.db_session_factory = db_session_factory
        app.state.db_engine = db_engine
        
        # Update rate limiting middleware with Redis client
        for middleware in app.user_middleware:
            if hasattr(middleware, 'cls') and middleware.cls == RateLimitMiddleware:
                middleware.kwargs['redis_client'] = redis_client
        
        # Initialize streaming service
        global streaming_service
        try:
            # Create dependencies
            audio_service = AudioService()
            text_service = TextService()
            voice_service = VoiceService()
            triton_url = os.getenv("TRITON_ENDPOINT", "http://localhost:8000")
            # Strip http:// or https:// scheme from URL (like ASR service)
            if triton_url.startswith(('http://', 'https://')):
                triton_url = triton_url.split('://', 1)[1]
            triton_api_key = os.getenv("TRITON_API_KEY")
            triton_client = TritonClient(triton_url, triton_api_key)
            
            # Create async session for repository
            async with db_session_factory() as session:
                repository = TTSRepository(session)
                
                # Create streaming service (if available)
                if STREAMING_AVAILABLE:
                    response_frequency_ms = int(os.getenv("STREAMING_RESPONSE_FREQUENCY_MS", "2000"))
                    streaming_service = StreamingTTSService(
                        audio_service=audio_service,
                        text_service=text_service,
                        triton_client=triton_client,
                        repository=repository,
                        voice_service=voice_service,
                        redis_client=redis_client,
                        response_frequency_in_ms=response_frequency_ms
                    )
                    
                    logger.info("TTS streaming service initialized successfully")
                    
                    # Mount Socket.IO streaming endpoint
                    app.mount("/socket.io/tts", streaming_service.app)
                    logger.info("Socket.IO TTS streaming endpoint mounted at /socket.io/tts")
                else:
                    logger.warning("Streaming service not available - socketio dependency missing")
        except Exception as e:
            logger.error(f"Failed to initialize streaming service: {e}")
            # Continue without streaming (optional feature)
        
        # Register service into the central registry via config-service
        try:
            global registry_client, registered_instance_id
            registry_client = ServiceRegistryHttpClient()
            service_name = os.getenv("SERVICE_NAME", "tts-service")
            service_port = int(os.getenv("SERVICE_PORT", "8088"))
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

        logger.info("TTS Service started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start TTS Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down TTS Service...")
    
    try:
        # Deregister from registry if previously registered
        try:
            if registry_client and registered_instance_id:
                service_name = os.getenv("SERVICE_NAME", "tts-service")
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
        
        logger.info("TTS Service shutdown complete")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Create FastAPI application
app = FastAPI(
    title="TTS Service",
    version="1.0.0",
    description="Text-to-Speech microservice for converting text to natural-sounding speech. Supports 22+ Indic Languages with multiple voice options and audio formats.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "TTS Inference",
            "description": "Text-to-speech conversion endpoints"
        },
        {
            "name": "Voice Management",
            "description": "Voice catalog and selection"
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

# Initialize Dhruva Observability Plugin
# Plugin automatically extracts metrics from request bodies - no manual recording needed!
config = PluginConfig.from_env()
config.enabled = True  # Enable plugin
if not config.customers:
    config.customers = []  # Will be extracted from JWT/headers automatically
if not config.apps:
    config.apps = ["tts"]  # Service name

plugin = ObservabilityPlugin(config)
plugin.register_plugin(app)
logger.info("✅ Dhruva Observability Plugin initialized for TTS service")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Add rate limiting middleware (will be configured with Redis in lifespan)
rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=rate_limit_per_minute,
    requests_per_hour=rate_limit_per_hour,
    redis_client=None  # Will be set in lifespan
)

# Register error handlers
add_error_handlers(app)

# Socket.IO streaming endpoint will be mounted after streaming service initialization


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint returning service information."""
    return {
        "service": "tts-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Text-to-Speech microservice"
    }


@app.get("/streaming/info")
async def streaming_info() -> Dict[str, Any]:
    """Get TTS streaming endpoint information."""
    if not streaming_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Streaming service not available"
        )
    
    return {
        "endpoint": "/socket.io/tts",
        "protocol": "Socket.IO",
        "events": {
            "client_to_server": ["start", "data", "disconnect"],
            "server_to_client": ["ready", "response", "error", "terminate"]
        },
        "connection_params": {
            "serviceId": "TTS model identifier (required)",
            "voice_id": "Voice identifier (required)",
            "language": "Language code (required)",
            "gender": "Voice gender (required)",
            "samplingRate": "Audio sample rate in Hz (optional, default: 22050)",
            "audioFormat": "Output audio format (optional, default: wav)",
            "apiKey": "API key for authentication (optional)"
        },
        "example_url": "ws://localhost:8088/socket.io/tts?serviceId=indic-tts-coqui-dravidian&voice_id=indic-tts-coqui-dravidian-female&language=ta&gender=female"
    }


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for service and dependencies."""
    health_status = {
        "status": "healthy",
        "service": "tts-service",
        "version": "1.0.0",
        "redis": "unhealthy",
        "postgres": "unhealthy",
        "triton": "unhealthy",
        "timestamp": None
    }
    
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
        logger.error(f"PostgreSQL health check failed: {e}")
        health_status["postgres"] = "unhealthy"
    
    try:
        # Check Triton server connectivity
        try:
            from utils.triton_client import TritonClient
            triton_url = os.getenv("TRITON_ENDPOINT", "http://localhost:8000")
            # Strip http:// or https:// scheme from URL (like ASR service)
            if triton_url.startswith(('http://', 'https://')):
                triton_url = triton_url.split('://', 1)[1]
            triton_api_key = os.getenv("TRITON_API_KEY")
            triton_client = TritonClient(triton_url, triton_api_key)
            
            # Check if server is ready
            if triton_client.is_server_ready():
                health_status["triton"] = "healthy"
            else:
                health_status["triton"] = "unhealthy"
        except ImportError:
            health_status["triton"] = "unavailable"
    except Exception as e:
        logger.error(f"Triton health check failed: {e}")
        health_status["triton"] = "unhealthy"
    
    # Determine overall status
    if health_status["redis"] == "healthy" and health_status["postgres"] == "healthy":
        health_status["status"] = "healthy"
    else:
        health_status["status"] = "unhealthy"
    
    return health_status


# Include routers
try:
    from routers.inference_router import inference_router
    from routers.health_router import health_router
    from routers.voice_router import router as voice_router
    
    app.include_router(inference_router)
    app.include_router(health_router)
    app.include_router(voice_router)
    
except ImportError as e:
    logger.warning(f"Could not import routers: {e}. Service will start without API endpoints.")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("SERVICE_PORT", "8088"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=log_level,
        reload=False
    )
