"""
Pipeline Service - Multi-task AI Pipeline Orchestration

Main FastAPI application entry point for the pipeline microservice.
Orchestrates multiple AI tasks in sequence (e.g., ASR → Translation → TTS).
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from utils.service_registry_client import ServiceRegistryHttpClient

# Import middleware components
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.error_handler_middleware import add_error_handlers
from middleware.request_logging import RequestLoggingMiddleware

# Import AI4ICore libraries for observability, logging, and tracing
try:
    from ai4icore_observability import ObservabilityPlugin, PluginConfig
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    logging.warning("ai4icore_observability not available, observability plugin disabled")

try:
    from ai4icore_logging import (
        get_logger,
        CorrelationMiddleware,
        configure_logging,
    )
    LOGGING_AVAILABLE = True
except ImportError:
    LOGGING_AVAILABLE = False
    logging.warning("ai4icore_logging not available, using standard logging")

try:
    from ai4icore_telemetry import setup_tracing
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logging.warning("ai4icore_telemetry not available, distributed tracing disabled")

# Configure structured logging
if LOGGING_AVAILABLE:
    configure_logging(
        service_name=os.getenv("SERVICE_NAME", "pipeline-service"),
        use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
    )
    logger = get_logger(__name__)
    
    # Aggressively disable uvicorn access logger BEFORE uvicorn starts
    # This must happen before uvicorn imports/creates its loggers
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True
    uvicorn_access.setLevel(logging.CRITICAL + 1)  # Set above CRITICAL to ensure nothing logs
    
    # Also disable at root level by filtering out uvicorn.access messages
    class UvicornAccessFilter(logging.Filter):
        """Filter to block uvicorn.access log messages."""
        def filter(self, record):
            # Block uvicorn.access logger
            if record.name == "uvicorn.access":
                return False
            # Also block messages that look like uvicorn access logs
            # Format: "INFO: IP:PORT "METHOD PATH HTTP/1.1" STATUS"
            message = str(record.getMessage())
            if 'HTTP/1.1"' in message:
                import re
                # Match uvicorn access log pattern: INFO: IP:PORT "METHOD PATH HTTP/1.1" STATUS
                if re.search(r'INFO:\s+\d+\.\d+\.\d+\.\d+:\d+\s+"(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+.*HTTP/1\.1"\s+\d+', message):
                    return False
            return True
    
    # Add filter to root logger to catch any uvicorn.access messages
    root_logger = logging.getLogger()
    uvicorn_filter = UvicornAccessFilter()
    for handler in root_logger.handlers:
        handler.addFilter(uvicorn_filter)
else:
    # Configure standard logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

# Global variable for Redis connection
redis_client: redis.Redis = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Pipeline Service...")
    
    global redis_client
    try:
        # Initialize Redis connection
        if redis_client is None:
            try:
                redis_host = os.getenv("REDIS_HOST", "redis")
                redis_port = int(os.getenv("REDIS_PORT_NUMBER", "6379"))
                redis_password = os.getenv("REDIS_PASSWORD", "redis_secure_password_2024")
                
                redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}"
                redis_client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
                
                # Test Redis connection
                await redis_client.ping()
                logger.info("Redis connection established successfully")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Rate limiting will be disabled.")
                redis_client = None
        
        # Store Redis client in app state for middleware access
        app.state.redis_client = redis_client
        
        # Register error handlers
        add_error_handlers(app)
        
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
        
        # Close Redis connection
        if redis_client:
            await redis_client.close()
            logger.info("Redis connection closed")
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
    contact={
        "name": "AI4ICore Team",
        "url": "https://github.com/AI4X",
        "email": "support@ai4x.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan
)

# Observability Plugin (OpenSearch metrics)
if OBSERVABILITY_AVAILABLE:
    try:
        config = PluginConfig.from_env()
        config.enabled = True
        if not config.customers:
            config.customers = []
        if not config.apps:
            config.apps = ["pipeline"]
        
        plugin = ObservabilityPlugin(config)
        plugin.register_plugin(app)
        logger.info("✅ AI4ICore Observability Plugin initialized for Pipeline service")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize observability plugin: {e}")

# Distributed Tracing (Jaeger)
# IMPORTANT: Setup tracing BEFORE instrumenting FastAPI
if TRACING_AVAILABLE:
    try:
        tracer = setup_tracing("pipeline-service")
        if tracer:
            logger.info("✅ Distributed tracing initialized for Pipeline service")
            # Instrument FastAPI to automatically create spans for all requests
            # Exclude health and metrics endpoints to reduce noise
            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls="/health,/metrics,/enterprise/metrics,/docs,/openapi.json,/redoc"
            )
            logger.info("✅ FastAPI instrumentation enabled for tracing")
            # NOTE: HTTPX auto-instrumentation is DISABLED to prevent duplicate spans
            # HTTPX instrumentation was creating duplicate "http receive/send" spans for the same endpoint
            # Instead, we use manual trace context propagation in http_client.py which properly
            # propagates trace context to downstream services without creating duplicate spans
            # The expected trace structure is:
            # - 1x "POST /api/v1/pipeline/inference http receive" (FastAPI - incoming request)
            # - 1x "pipeline.authentication" (manual span)
            # - 1x "pipeline.run_inference" (manual span)
            # - Nx "pipeline.task.{taskType}" (manual spans, one per task)
            # Downstream services (ASR/NMT/TTS) will create their own spans via FastAPI instrumentation
            # HTTPXClientInstrumentor().instrument()  # DISABLED to prevent duplicate spans
            logger.info("✅ HTTPX auto-instrumentation disabled (using manual trace context propagation)")
        else:
            logger.warning("⚠️ Tracing setup returned None")
    except Exception as e:
        logger.warning(f"⚠️ Failed to setup tracing: {e}")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Correlation middleware (MUST be added if logging is available)
# This extracts X-Correlation-ID from headers and sets it in logging context
if LOGGING_AVAILABLE:
    app.add_middleware(CorrelationMiddleware)
    logger.info("✅ Correlation middleware added for distributed tracing")
    
    # Request logging middleware (MUST be after CorrelationMiddleware)
    # This logs API requests and errors to OpenSearch
    app.add_middleware(RequestLoggingMiddleware)
    logger.info("✅ Request logging middleware added for API request tracking")

# Add rate limiting middleware
# Redis client will be initialized in lifespan and stored in app.state
# The middleware will access it from app.state
rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
app.add_middleware(
    RateLimitMiddleware,
    redis_client=None,  # Will be accessed from app.state in middleware
    requests_per_minute=rate_limit_per_minute,
    requests_per_hour=rate_limit_per_hour
)
logger.info("Rate limiting middleware added (Redis will be initialized in lifespan)")


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
        "redis": "unhealthy",
        "dependencies": {}
    }
    
    try:
        import time
        health_status["timestamp"] = time.time()
        
        # Check Redis connectivity
        global redis_client
        if redis_client:
            try:
                await redis_client.ping()
                health_status["redis"] = "healthy"
            except Exception as e:
                logger.error(f"Redis health check failed: {e}")
                health_status["redis"] = "unhealthy"
        else:
            health_status["redis"] = "unavailable"
        
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
