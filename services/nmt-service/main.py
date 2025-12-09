"""
NMT Service - Neural Machine Translation microservice
Main FastAPI application entry point
"""

import asyncio
import logging
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

# Load environment variables from .env file if it exists
load_dotenv()

from routers import health_router, inference_router
from utils.service_registry_client import ServiceRegistryHttpClient
from utils.triton_client import TritonClient
from utils.model_management_client import ModelManagementClient
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

# Environment variables - Support both REDIS_PORT and REDIS_PORT_NUMBER for backward compatibility
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT") or os.getenv("REDIS_PORT_NUMBER", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
REDIS_TIMEOUT = int(os.getenv("REDIS_TIMEOUT", "10"))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db"
)
TRITON_ENDPOINT = os.getenv("TRITON_ENDPOINT", "13.200.133.97:8000")
TRITON_API_KEY = os.getenv("TRITON_API_KEY", "1b69e9a1a24466c85e4bbca3c5295f50")
MODEL_MANAGEMENT_SERVICE_URL = os.getenv("MODEL_MANAGEMENT_SERVICE_URL", "http://model-management-service:8000")
MODEL_MANAGEMENT_SERVICE_API_KEY = os.getenv("MODEL_MANAGEMENT_SERVICE_API_KEY", None)
MODEL_MANAGEMENT_CACHE_TTL = int(os.getenv("MODEL_MANAGEMENT_CACHE_TTL", "300"))  # 5 minutes default

# Global variables
redis_client: Optional[redis.Redis] = None
db_engine: Optional[AsyncEngine] = None
db_session_factory: Optional[async_sessionmaker] = None
registry_client: Optional[ServiceRegistryHttpClient] = None
registered_instance_id: Optional[str] = None
model_management_client: Optional[ModelManagementClient] = None

logger.info(f"Configuration loaded: REDIS_HOST={REDIS_HOST}, REDIS_PORT={REDIS_PORT}")
logger.info(f"DATABASE_URL configured: {DATABASE_URL.split('@')[0]}@***")  # Mask password in logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown"""
    global redis_client, db_engine, db_session_factory, registry_client, registered_instance_id, model_management_client

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

    # Initialize Model Management Service Client
    try:
        model_management_client = ModelManagementClient(
            base_url=MODEL_MANAGEMENT_SERVICE_URL,
            api_key=MODEL_MANAGEMENT_SERVICE_API_KEY,
            cache_ttl_seconds=MODEL_MANAGEMENT_CACHE_TTL,
            timeout=10.0
        )
        logger.info(f"Model Management Service client initialized: {MODEL_MANAGEMENT_SERVICE_URL}")
    except Exception as e:
        logger.warning(f"Failed to initialize Model Management Service client: {e}")
        model_management_client = None
    
    # Store in app state for middleware & routes
    app.state.redis_client = redis_client
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    app.state.triton_endpoint = TRITON_ENDPOINT
    app.state.triton_api_key = TRITON_API_KEY
    app.state.model_management_client = model_management_client

    # Register service into the central registry via config-service
    try:
        registry_client = ServiceRegistryHttpClient()
        service_name = os.getenv("SERVICE_NAME", "nmt-service")
        service_port = int(os.getenv("SERVICE_PORT", "8089"))
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

    logger.info("✅ NMT Service started successfully")

    # ---- Application is now up ----
    yield

    # Shutdown
    logger.info("Shutting down NMT Service...")

    try:
        # Deregister from registry if previously registered
        try:
            if registry_client and registered_instance_id:
                service_name = os.getenv("SERVICE_NAME", "nmt-service")
                await registry_client.deregister(service_name, registered_instance_id)
        except Exception as e:
            logger.warning("Service registry deregistration error: %s", e)

        if redis_client:
            await redis_client.close()
            logger.info("Redis connection closed")

        if db_engine:
            await db_engine.dispose()
            logger.info("PostgreSQL connection closed")
        
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
    contact={
        "name": "Dhruva Platform Team",
        "url": "https://github.com/AI4Bharat/Dhruva",
        "email": "support@dhruva-platform.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
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
    try:
        rc = getattr(request.app.state, "redis_client", None)
        if rc is not None:
            await rc.ping()
            redis_ok = True
    except Exception as e:
        logger.warning(f"/health: Redis check failed: {e}")

    # Check DB
    try:
        session_factory = getattr(request.app.state, "db_session_factory", None)
        if session_factory is not None:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
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
    uvicorn.run(app, host="0.0.0.0", port=8089)
