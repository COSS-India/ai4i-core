from fastapi import FastAPI
from contextlib import asynccontextmanager
from logger import logger
from db_connection import create_tables , auth_db_engine, AuthDBSessionLocal , tenant_db_engine , TenantDBSessionLocal
import uvicorn

from routers.admin_router import router as admin_router
from routers.billing_router import router as billing_router
from routers.email_router import router as email_router
from routers.tenant_router import router as tenant_router
from routers.service_router import router as service_router

from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.request_logging import RequestLoggingMiddleware
from middleware.error_handler_middleware import add_error_handlers
from cache.app_cache import get_cache_connection, get_async_cache_connection

import os

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))

# Sync Redis client for redis_om (model/service caching)
redis_cache_client = get_cache_connection()

# Async Redis client for auth and rate limiting
redis_client = get_async_cache_connection()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FastAPI app initialization...")

    # 1. Create APP DB (sync) tables
    await create_tables()
    logger.info("Tenant DB tables verified or created.")


    app.state.auth_db_engine = auth_db_engine
    app.state.app_db_engine = tenant_db_engine
    app.state.auth_session_factory = AuthDBSessionLocal
    app.state.app_session_factory = TenantDBSessionLocal

    yield   # everything before this runs at startup; everything after runs at shutdown
    logger.info("Shutting down FastAPI app...")

    # Close sync Redis client (for redis_om caching)
    try:
        if redis_cache_client:
            redis_cache_client.close()
            logger.info("Sync Redis connection closed.")
    except Exception as e:
        logger.error(f"Error closing sync Redis: {e}")

    # Close async Redis client (for auth/rate limiting)
    try:
        if redis_client:
            await redis_client.close()
            logger.info("Async Redis connection closed.")
    except Exception as e:
        logger.error(f"Error closing async Redis: {e}")

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
    title="Multi Tenant Service API",
    version="1.0.0",
    description="API for creating and managing models",
    lifespan=lifespan,  # use lifespan instead of @on_event
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
app.include_router(admin_router)
# app.include_router(billing_router) # TODO add if required
app.include_router(email_router)
app.include_router(tenant_router)
app.include_router(service_router)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "multi-tenant-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Multi tenant support feature"
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "multi-tenant-service"}


if __name__ == "__main__":
    logger.info(" Starting FastAPI server on http://0.0.0.0:8001 ...")
    uvicorn.run("main:app", host="0.0.0.0", port=8001, loop="asyncio", reload=True)