"""FastAPI application for Translation Request Profiler with enhanced error handling."""
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import Response

from .config import settings
from .errors import (
    BatchSizeExceededError,
    DataQualityError,
    ModelError,
    ModelNotLoadedError,
    ProfilerError,
    RateLimitError,
    ServiceUnavailableError,
    TimeoutError,
    ValidationError,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
from .metrics import (
    BATCH_SIZE,
    MODEL_VERSION,
    PROFILE_LATENCY,
    PROFILE_REQUESTS,
    TEXT_LENGTH,
)
from .profiler import profiler
from .schemas import (
    BatchProfileRequest,
    BatchProfileResponse,
    HealthResponse,
    InfoResponse,
    ProfileRequest,
    ProfileResponse,
    ResponseMetadata,
)


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle with comprehensive error handling."""
    # Startup
    logger.info("=" * 70)
    logger.info("Translation Request Profiler - Starting Up")
    logger.info("=" * 70)

    app.state.start_time = time.time()
    app.state.healthy = False

    try:
        logger.info("Loading ML models...")
        profiler.load_models()

        MODEL_VERSION.info({
            "version": profiler.model_version,
            "domain_model": str(settings.domain_model_path),
            "complexity_model": str(settings.complexity_model_path),
        })

        app.state.healthy = True
        logger.info("✓ Service ready and healthy")
        logger.info(f"Model version: {profiler.model_version}")

    except FileNotFoundError as e:
        logger.error(f"✗ Model files not found: {e}")
        logger.error("Please ensure models are trained and available")
        raise
    except Exception as e:
        logger.error(f"✗ Failed to start service: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down gracefully...")
    app.state.healthy = False

    # Shutdown
    print("Shutting down...")


# Initialize FastAPI app
app = FastAPI(
    title="Translation Request Profiler",
    description="ML-powered profiling service for translation requests",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Middleware for request ID and timing
@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    """Add request ID and timing to all requests."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{duration:.4f}"
    
    return response


# ── Enhanced Exception Handlers ──────────────────────────────────────


@app.exception_handler(ProfilerError)
async def profiler_error_handler(request: Request, exc: ProfilerError):
    """
    Comprehensive handler for all ProfilerError types.
    Returns structured error response with full context.
    """
    request_id = getattr(request.state, 'request_id', 'unknown')

    logger.error(
        f"ProfilerError [{exc.code}] - Request ID: {request_id} - {exc.message}",
        extra={
            "request_id": request_id,
            "error_code": exc.code,
            "severity": exc.severity.value,
            "details": exc.details
        }
    )

    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict()
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """Handle validation errors with detailed feedback."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.warning(f"Validation error - Request ID: {request_id} - {exc.message}")

    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict()
    )


@app.exception_handler(ModelNotLoadedError)
async def model_not_loaded_handler(request: Request, exc: ModelNotLoadedError):
    """Handle model not loaded errors."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(f"Models not loaded - Request ID: {request_id}")

    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict()
    )


@app.exception_handler(ModelError)
async def model_error_handler(request: Request, exc: ModelError):
    """Handle model prediction errors."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(
        f"Model error - Request ID: {request_id} - {exc.message}",
        extra={"details": exc.details}
    )

    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict()
    )


@app.exception_handler(RateLimitError)
async def rate_limit_error_handler(request: Request, exc: RateLimitError):
    """Handle rate limit errors."""
    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict(),
        headers={"Retry-After": str(exc.details.get("retry_after", 60))}
    )


@app.exception_handler(BatchSizeExceededError)
async def batch_size_error_handler(request: Request, exc: BatchSizeExceededError):
    """Handle batch size errors."""
    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict()
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Catch-all handler for unexpected exceptions.
    Ensures no unhandled errors crash the service.
    """
    request_id = getattr(request.state, 'request_id', 'unknown')

    logger.error(
        f"Unexpected error - Request ID: {request_id} - {type(exc).__name__}: {exc}",
        exc_info=True
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "request_id": request_id,
                "timestamp": time.time()
            }
        }
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "batch_size_exceeded", "message": str(exc)},
    )


@app.exception_handler(ProfilerError)
async def profiler_error_handler(request: Request, exc: ProfilerError):
    """Handle generic profiler errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "profiler_error", "message": str(exc)},
    )


# ── API Endpoints ──────────────────────────────────────────────────────────────


@app.post("/api/v1/profile", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def profile_text(request: Request, profile_request: ProfileRequest) -> ProfileResponse:
    """Profile a single translation request.

    Args:
        profile_request: Request containing text and options

    Returns:
        ProfileResponse with complete profiling results

    Raises:
        ValidationError: If input validation fails
        ModelError: If profiling fails
    """
    start_time = time.time()

    # Validate text length
    text = profile_request.text.strip()
    word_count = len(text.split())

    if len(text) < 1 or len(text) > settings.max_text_length:
        raise ValidationError(f"Text length must be between 1 and {settings.max_text_length} characters")

    if word_count < 2:
        raise ValidationError("Text must contain at least 2 words")

    # Sanitize HTML/scripts (basic)
    if "<script" in text.lower() or "<iframe" in text.lower():
        raise ValidationError("HTML scripts are not allowed")

    # Profile the text
    try:
        options = profile_request.options
        result = profiler.profile(
            text=text,
            include_entities=options.include_entities if options else True,
            include_language=options.include_language_detection if options else True,
        )

        # Record metrics
        duration = time.time() - start_time
        PROFILE_LATENCY.observe(duration)
        TEXT_LENGTH.observe(word_count)
        PROFILE_REQUESTS.labels(
            domain=result.domain.label,
            complexity_level=result.scores.complexity_level,
            status="success",
        ).inc()

        # Build response
        from datetime import datetime, timezone
        metadata = ResponseMetadata(
            model_version=profiler.model_version,
            processing_time_ms=int(round(duration * 1000)),
            timestamp=datetime.now(timezone.utc),
        )

        return ProfileResponse(
            request_id=request.state.request_id,
            profile=result,
            metadata=metadata,
        )

    except Exception as e:
        PROFILE_REQUESTS.labels(
            domain="unknown",
            complexity_level="unknown",
            status="error",
        ).inc()
        raise ModelError(f"Profiling failed: {e}")


@app.post("/api/v1/profile/batch", response_model=BatchProfileResponse, status_code=status.HTTP_200_OK)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def profile_batch(request: Request, batch_request: BatchProfileRequest) -> BatchProfileResponse:
    """Profile multiple translation requests in batch.

    Args:
        batch_request: Request containing list of texts

    Returns:
        BatchProfileResponse with results for all texts

    Raises:
        BatchSizeExceededError: If batch size exceeds limit
        ValidationError: If input validation fails
    """
    start_time = time.time()

    # Validate batch size
    if len(batch_request.texts) > settings.max_batch_size:
        raise BatchSizeExceededError(
            f"Batch size {len(batch_request.texts)} exceeds maximum {settings.max_batch_size}"
        )

    BATCH_SIZE.observe(len(batch_request.texts))

    # Profile each text
    results = []
    errors = []

    for idx, text in enumerate(batch_request.texts):
        try:
            text = text.strip()
            if len(text) < 1 or len(text) > settings.max_text_length:
                errors.append({"index": idx, "error": "Invalid text length"})
                results.append(None)
                continue

            result = profiler.profile(text=text)
            results.append(result)

            # Record metrics
            PROFILE_REQUESTS.labels(
                domain=result.domain.label,
                complexity_level=result.scores.complexity_level,
                status="success",
            ).inc()

        except Exception as e:
            errors.append({"index": idx, "error": str(e)})
            results.append(None)
            PROFILE_REQUESTS.labels(
                domain="unknown",
                complexity_level="unknown",
                status="error",
            ).inc()

    # Build response
    duration = time.time() - start_time
    PROFILE_LATENCY.observe(duration)

    from datetime import datetime, timezone
    metadata = ResponseMetadata(
        model_version=profiler.model_version,
        processing_time_ms=int(round(duration * 1000)),
        timestamp=datetime.now(timezone.utc),
    )

    return BatchProfileResponse(
        request_id=request.state.request_id,
        profiles=results,
        metadata=metadata,
    )


@app.get("/api/v1/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check() -> HealthResponse:
    """Basic health check endpoint."""
    from datetime import datetime, timezone
    return HealthResponse(
        status="healthy",
        models_loaded=profiler.models_loaded,
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/api/v1/health/ready", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def readiness_check() -> HealthResponse:
    """Readiness probe - checks if models are loaded."""
    from datetime import datetime, timezone
    if not profiler.models_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Models not loaded",
        )
    return HealthResponse(
        status="ready",
        models_loaded=True,
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/api/v1/info", response_model=InfoResponse, status_code=status.HTTP_200_OK)
async def service_info() -> InfoResponse:
    """Get service information and capabilities."""
    import time
    return InfoResponse(
        service_name="Translation Request Profiler",
        service_version="1.0.0",
        model_version=profiler.model_version,
        uptime_seconds=time.time() - app.state.start_time if hasattr(app.state, "start_time") else 0.0,
        models_loaded=profiler.models_loaded,
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

