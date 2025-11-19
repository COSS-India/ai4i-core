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
from utils.service_registry_client import ServiceRegistryHttpClient

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
        # Register service into the central registry via config-service
        registry_client = ServiceRegistryHttpClient()
        service_name = os.getenv("SERVICE_NAME", "pipeline-service")
        service_port = int(os.getenv("SERVICE_PORT", "8090"))
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

        logger.info("Pipeline Service started successfully")
    except Exception as e:
        logger.error(f"Failed to start Pipeline Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Pipeline Service...")
    try:
        # Deregister service (best-effort)
        try:
            registry_client = ServiceRegistryHttpClient()
            service_name = os.getenv("SERVICE_NAME", "pipeline-service")
            instance_id = os.getenv("SERVICE_INSTANCE_ID", f"{service_name}-{os.getpid()}")
            if instance_id:
                await registry_client.deregister(service_name, instance_id)
        except Exception:
            pass
    finally:
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
        "timestamp": None,
        "dependencies": {}
    }
    
    try:
        import time
        health_status["timestamp"] = time.time()
        
        # Resolve service URLs via registry (no hardcoded fallbacks)
        registry = ServiceRegistryHttpClient()
        
        # Discover services via registry
        asr_env = os.getenv('ASR_SERVICE_URL')
        nmt_env = os.getenv('NMT_SERVICE_URL')
        tts_env = os.getenv('TTS_SERVICE_URL')
        
        if asr_env:
            asr_url = asr_env.rstrip('/')
            health_status["dependencies"]["asr_service"] = asr_url
            health_status["dependencies"]["asr_service_source"] = "environment"
        else:
            asr_url = await registry.discover_url('asr-service')
            if asr_url:
                health_status["dependencies"]["asr_service"] = asr_url.rstrip('/')
                health_status["dependencies"]["asr_service_source"] = "registry"
            else:
                health_status["dependencies"]["asr_service"] = None
                health_status["dependencies"]["asr_service_source"] = "not_found"
                health_status["status"] = "unhealthy"
        
        if nmt_env:
            nmt_url = nmt_env.rstrip('/')
            health_status["dependencies"]["nmt_service"] = nmt_url
            health_status["dependencies"]["nmt_service_source"] = "environment"
        else:
            nmt_url = await registry.discover_url('nmt-service')
            if nmt_url:
                health_status["dependencies"]["nmt_service"] = nmt_url.rstrip('/')
                health_status["dependencies"]["nmt_service_source"] = "registry"
            else:
                health_status["dependencies"]["nmt_service"] = None
                health_status["dependencies"]["nmt_service_source"] = "not_found"
                health_status["status"] = "unhealthy"
        
        if tts_env:
            tts_url = tts_env.rstrip('/')
            health_status["dependencies"]["tts_service"] = tts_url
            health_status["dependencies"]["tts_service_source"] = "environment"
        else:
            tts_url = await registry.discover_url('tts-service')
            if tts_url:
                health_status["dependencies"]["tts_service"] = tts_url.rstrip('/')
                health_status["dependencies"]["tts_service_source"] = "registry"
            else:
                health_status["dependencies"]["tts_service"] = None
                health_status["dependencies"]["tts_service_source"] = "not_found"
                health_status["status"] = "unhealthy"
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)
    
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
