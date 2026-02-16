"""
Alert Management Service
Provides CRUD operations for alert definitions, notification receivers, and routing rules.
"""
import os

from ai4icore_logging import get_logger, configure_logging

# Configure structured logging (same approach as nmt-service, ocr-service)
configure_logging(
    service_name=os.getenv("SERVICE_NAME", "alert-management-service"),
    use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
)

# Disable uvicorn access logger before uvicorn starts
import logging
uvicorn_access = logging.getLogger("uvicorn.access")
uvicorn_access.handlers.clear()
uvicorn_access.propagate = False
uvicorn_access.disabled = True
uvicorn_access.setLevel(logging.CRITICAL + 1)

logger = get_logger(__name__)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from alert_management import init_db_pool, close_db_pool
from routers.alert_definitions import router as alert_definitions_router
from routers.receivers import router as receivers_router
from routers.routing_rules import router as routing_rules_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    logger.info("Starting Alert Management Service...", extra={"context": {"event": "startup"}})

    # Initialize database connection pool
    try:
        await init_db_pool()
        logger.info("Database connection pool initialized", extra={"context": {"event": "db_pool_ready"}})
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}", extra={"context": {"error": str(e)}})
        raise

    yield

    # Shutdown
    logger.info("Shutting down Alert Management Service...", extra={"context": {"event": "shutdown"}})
    try:
        await close_db_pool()
        logger.info("Database connection pool closed", extra={"context": {"event": "db_pool_closed"}})
    except Exception as e:
        logger.warning(f"Error closing database pool: {e}", extra={"context": {"error": str(e)}})


app = FastAPI(
    title="Alert Management Service API",
    version="1.0.0",
    description="API for managing alert definitions, notification receivers, and routing rules",
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

# Register routers
app.include_router(alert_definitions_router)
app.include_router(receivers_router)
app.include_router(routing_rules_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "alert-management-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Alert management API for dynamic alert configuration"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "alert-management-service"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8098"))
    logger.info(
        f"Starting Alert Management Service on http://0.0.0.0:{port}...",
        extra={"context": {"port": port}}
    )
    uvicorn.run("main:app", host="0.0.0.0", port=port, loop="asyncio", reload=True)

