from fastapi import FastAPI
from contextlib import asynccontextmanager
from logger import logger
from db_connection import create_tables , auth_db_engine, AuthDBSessionLocal , app_db_engine , AppDBSessionLocal
from routers.router_admin import router_admin
from routers.router_details import router_details
from routers.router_health import router_health
from cache.app_cache import get_cache_connection, get_async_cache_connection
import uvicorn
import os

from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.error_handler_middleware import add_error_handlers



RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))

# Sync Redis client for redis_om (model/service caching)
redis_cache_client = get_cache_connection()

# Async Redis client for auth and rate limiting
redis_client = get_async_cache_connection()

# -----------------------------
# Lifespan Event Handler (replaces @app.on_event)
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FastAPI app initialization...")

    # 1. Create APP DB (sync) tables
    await create_tables()
    logger.info("App DB tables verified or created.")


    app.state.auth_db_engine = auth_db_engine
    app.state.app_db_engine = app_db_engine
    app.state.auth_session_factory = AuthDBSessionLocal
    app.state.app_session_factory = AppDBSessionLocal
    app.state.redis_client = redis_client  # Async client for auth/rate limiting
    app.state.redis_cache_client = redis_cache_client  # Sync client for redis_om (already set in CacheBaseModel)

    yield   # everything before this runs at startup; everything after runs at shutdown


    logger.info("Shutting down FastAPI app...")
    
    # Close sync Redis client (for redis_om caching)
    try:
        if redis_cache_client:
            redis_cache_client.close()
            logger.info("Sync Redis connection closed.")
    except Exception as e:
        logger.error(f"Error closing sync Redis: {e}")

    # Dispose async auth engine
    try:
        if app.state.auth_db_engine:
            await app.state.auth_db_engine.dispose()
            logger.info("Auth DB engine disposed.")
    except Exception as e:
        logger.error(f"Error disposing Auth DB: {e}")

    # Dispose async auth engine
    try:
        if app.state.app_db_engine:
            await app.state.app_db_engine.dispose()
            logger.info("Model management DB engine disposed.")
    except Exception as e:
        logger.error(f"Error disposing Model management DB: {e}")

    logger.info("Shutdown complete.")



app = FastAPI(
    title="Model Management Service API",
    version="1.0.0",
    description="API for creating and managing models",
    lifespan=lifespan,  # ✅ use lifespan instead of @on_event
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
    rate_limit_per_minute = RATE_LIMIT_PER_MINUTE
    rate_limit_per_hour = RATE_LIMIT_PER_HOUR
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

# Register routers
app.include_router(router_admin)
app.include_router(router_details)
app.include_router(router_health)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "model-management-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Model Management microservice"
    }




if __name__ == "__main__":
    logger.info(" Starting FastAPI server on http://0.0.0.0:8000 ...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    