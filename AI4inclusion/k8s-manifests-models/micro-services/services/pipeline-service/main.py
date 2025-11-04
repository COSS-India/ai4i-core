"""
Pipeline Service - Multi-task AI Pipeline Orchestration

Main FastAPI application entry point for the pipeline microservice.
Orchestrates multiple AI tasks in sequence (e.g., ASR → Translation → TTS).
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Pipeline Service...")
    
    try:
        logger.info("Pipeline Service started successfully")
    except Exception as e:
        logger.error(f"Failed to start Pipeline Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Pipeline Service...")
    logger.info("Pipeline Service shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Pipeline Service",
    version="1.0.0",
    description="Multi-task AI pipeline orchestration microservice. Supports Speech-to-Speech translation and other multi-stage AI workflows.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "Pipeline",
            "description": "Pipeline inference endpoints for multi-task AI workflows"
        },
        {
            "name": "Health",
            "description": "Service health and readiness checks"
        }
    ],
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


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint returning service information."""
    return {
        "name": "Pipeline Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Multi-task AI pipeline orchestration microservice"
    }


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for service and dependencies."""
    health_status = {
        "status": "healthy",
        "service": "pipeline-service",
        "version": "1.0.0",
        "timestamp": None
    }
    
    try:
        import time
        health_status["timestamp"] = time.time()
        
        # Check service URLs
        asr_url = os.getenv('ASR_SERVICE_URL', 'http://asr-service:8087')
        nmt_url = os.getenv('NMT_SERVICE_URL', 'http://nmt-service:8089')
        tts_url = os.getenv('TTS_SERVICE_URL', 'http://tts-service:8088')
        
        health_status["dependencies"] = {
            "asr_service": asr_url,
            "nmt_service": nmt_url,
            "tts_service": tts_url
        }
        
        health_status["status"] = "healthy"
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_status["status"] = "unhealthy"
    
    return health_status


@app.get("/ready")
async def readiness_check() -> Dict[str, Any]:
    """Readiness check endpoint."""
    return {
        "status": "ready",
        "service": "pipeline-service"
    }


@app.get("/live")
async def liveness_check() -> Dict[str, Any]:
    """Liveness check endpoint."""
    return {
        "status": "alive",
        "service": "pipeline-service"
    }


# Include routers
try:
    from routers.pipeline_router import pipeline_router
    app.include_router(pipeline_router)
except ImportError as e:
    logger.warning(f"Could not import pipeline router: {e}. Service will start without API endpoints.")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("SERVICE_PORT", "8090"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=log_level,
        reload=False
    )
