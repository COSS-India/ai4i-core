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

from routers.health_router import health_router
from routers.inference_router import inference_router
from utils.triton_client import TritonClient
from middleware.auth_provider import AuthProvider
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.error_handler_middleware import add_error_handlers
from middleware.exceptions import AuthenticationError, AuthorizationError, RateLimitExceededError

# Import models to ensure they are registered with SQLAlchemy
from models import database_models, auth_models

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db")
TRITON_ENDPOINT = os.getenv("TRITON_ENDPOINT", "http://13.220.11.146:8000")
TRITON_API_KEY = os.getenv("TRITON_API_KEY", "")

# Global variables
redis_client: Optional[redis.Redis] = None
db_engine: Optional[AsyncEngine] = None
db_session_factory: Optional[async_sessionmaker] = None

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
    global redis_client, db_engine, db_session_factory
    
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
        
        logger.info("LLM Service started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start LLM Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down LLM Service...")
    
    try:
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
    description="Large Language Model microservice for text processing, translation, and generation. Supports multiple Indian languages.",
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

