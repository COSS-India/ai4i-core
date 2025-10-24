"""
ASR Service - Automatic Speech Recognition Microservice

Main FastAPI application entry point for the ASR microservice.
Provides batch ASR inference using Triton Inference Server.
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

# Import streaming service components
from services.streaming_service import StreamingASRService
from services.audio_service import AudioService
from utils.triton_client import TritonClient
from repositories.asr_repository import ASRRepository

# Import middleware components
from middleware.auth_provider import AuthProvider
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.error_handler_middleware import add_error_handlers
from middleware.exceptions import AuthenticationError, AuthorizationError, RateLimitExceededError

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
streaming_service: StreamingASRService = None


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
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
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
        
        # Initialize streaming service
        global streaming_service
        try:
            # Create dependencies
            audio_service = AudioService()
            triton_url = os.getenv("TRITON_ENDPOINT", "http://localhost:8000")
            # Strip http:// or https:// scheme from URL
            if triton_url.startswith(('http://', 'https://')):
                triton_url = triton_url.split('://', 1)[1]
            triton_api_key = os.getenv("TRITON_API_KEY")
            triton_client = TritonClient(triton_url, triton_api_key)
            
            # Create async session for repository
            async with db_session_factory() as session:
                repository = ASRRepository(session)
                
                # Create streaming service
                response_frequency_ms = int(os.getenv("STREAMING_RESPONSE_FREQUENCY_MS", "2000"))
                streaming_service = StreamingASRService(
                    audio_service=audio_service,
                    triton_client=triton_client,
                    repository=repository,
                    redis_client=redis_client,
                    response_frequency_in_ms=response_frequency_ms
                )
                
                logger.info("Streaming service initialized successfully")
                
                # Mount Socket.IO streaming endpoint
                app.mount("/socket.io", streaming_service.app)
                logger.info("Socket.IO streaming endpoint mounted at /socket.io")
        except Exception as e:
            logger.error(f"Failed to initialize streaming service: {e}")
            # Continue without streaming (optional feature)
        
        # Store connections in app state for middleware access
        app.state.redis_client = redis_client
        app.state.db_session_factory = db_session_factory
        
        # Register error handlers
        add_error_handlers(app)
        
        logger.info("ASR Service started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start ASR Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down ASR Service...")
    
    try:
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
    description="Automatic Speech Recognition microservice for converting speech to text. Supports 22+ Indian languages with real-time streaming and batch processing.",
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
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
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
    
    # Test Redis connection
    redis_client.ping()
    logger.info("Redis connection established for middleware")
except Exception as e:
    logger.warning(f"Redis connection failed for middleware: {e}")
    redis_client = None

# Add middleware after FastAPI app creation
# Add request logging middleware
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
        "description": "Automatic Speech Recognition microservice"
    }


@app.get("/streaming/info")
async def streaming_info() -> Dict[str, Any]:
    """Get streaming endpoint information."""
    if not streaming_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Streaming service not available"
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
        # Check Triton server connectivity (placeholder - will be implemented in utils)
        # For now, mark as healthy if we can import triton client
        try:
            import tritonclient.http as http_client
            health_status["triton"] = "healthy"
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
    
    app.include_router(inference_router)
    app.include_router(health_router)
    
except ImportError as e:
    logger.warning(f"Could not import routers: {e}. Service will start without API endpoints.")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("SERVICE_PORT", "8087"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=log_level,
        reload=False
    )
