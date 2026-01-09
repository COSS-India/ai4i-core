"""
FastAPI router for ASR inference endpoints.
"""

import logging
import time
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.asr_request import ASRInferenceRequest
from models.asr_response import ASRInferenceResponse
from repositories.asr_repository import ASRRepository, get_db_session
from services.asr_service import ASRService
from services.audio_service import AudioService
from utils.triton_client import TritonClient
from utils.validation_utils import (
    validate_language_code,
    validate_service_id,
    validate_audio_input,
    validate_preprocessors,
    validate_postprocessors,
    InvalidLanguageCodeError
)
from middleware.exceptions import AuthenticationError, AuthorizationError
from middleware.auth_provider import AuthProvider

# Import OpenTelemetry for manual span creation
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

logger = logging.getLogger(__name__)

# Create router with authentication dependency
inference_router = APIRouter(
    prefix="/api/v1/asr",
    tags=["ASR Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_asr_service(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> ASRService:
    """
    Dependency to get configured ASR service.
    
    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    repository = ASRRepository(db)
    audio_service = AudioService()
    
    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.app.state, "triton_api_key", "")
    triton_timeout = getattr(request.app.state, "triton_timeout", 300.0)
    
    if not triton_endpoint:
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        
        if service_id:
            error_detail = (
                f"Model Management failed to resolve Triton endpoint for serviceId: {service_id}. "
                f"Please ensure the service is registered in Model Management database."
            )
            if model_mgmt_error:
                error_detail += f" Error: {model_mgmt_error}"
            raise HTTPException(
                status_code=500,
                detail=error_detail,
            )
        raise HTTPException(
            status_code=400,
            detail=(
                "Request must include config.serviceId. "
                "ASR service requires Model Management database resolution."
            ),
        )
    
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        error_detail = (
            f"Model Management failed to resolve Triton model name for serviceId: {service_id}. "
            f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
        )
        if model_mgmt_error:
            error_detail += f" Error: {model_mgmt_error}"
        logger.error(error_detail)
        raise HTTPException(
            status_code=500,
            detail=error_detail,
        )
    
    logger.info(
        "Using Triton endpoint=%s model_name=%s for serviceId=%s from Model Management",
        triton_endpoint,
        model_name,
        getattr(request.state, "service_id", "unknown"),
    )
    
    # Strip http:// or https:// scheme from URL if present (TritonClient expects host:port)
    triton_url = triton_endpoint
    if triton_url.startswith(('http://', 'https://')):
        triton_url = triton_url.split('://', 1)[1]
    
    triton_client = TritonClient(triton_url, triton_api_key)
    
    # Pass resolved model_name to ASR service
    return ASRService(repository, audio_service, triton_client, resolved_model_name=model_name)


@inference_router.post(
    "/inference",
    response_model=ASRInferenceResponse,
    summary="Perform batch ASR inference",
    description="Convert speech to text for one or more audio inputs"
)
async def run_inference(
    request: ASRInferenceRequest,
    http_request: Request,
    asr_service: ASRService = Depends(get_asr_service)
) -> ASRInferenceResponse:
    """Run ASR inference on audio inputs."""
    start_time = time.time()
    request_id = None

    # Create a descriptive span for ASR inference when tracing is enabled
    if TRACING_AVAILABLE:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("ASR Inference") as span:
            span.set_attribute("service.name", "asr")
            span.set_attribute("service.type", "asr")
            span.set_attribute("asr.audio_count", len(request.audio))
            try:
                span.set_attribute("asr.service_id", request.config.serviceId)
                span.set_attribute("asr.language", request.config.language.sourceLanguage)
            except Exception:
                # Config may be missing or malformed; don't fail tracing because of this
                pass
            return await _run_asr_inference_internal(request, http_request, asr_service, start_time)
    else:
        return await _run_asr_inference_internal(request, http_request, asr_service, start_time)


async def _run_asr_inference_internal(
    request: ASRInferenceRequest,
    http_request: Request,
    asr_service: ASRService,
    start_time: float,
) -> ASRInferenceResponse:
    """Internal ASR inference logic with validation and rich error mapping."""
    try:
        # Extract auth context from request.state
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        session_id = getattr(http_request.state, "session_id", None)

        # Validate request
        await validate_request(request)

        # Log request
        logger.info(
            "Processing ASR inference request with %d audio inputs - user_id=%s api_key_id=%s",
            len(request.audio),
            user_id,
            api_key_id,
        )

        # Run inference with auth context
        response = await asr_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
        )

        # Log completion
        processing_time = time.time() - start_time
        logger.info("ASR inference completed in %.2fs", processing_time)

        # Debug: Log response structure
        logger.info("Response contains %d transcript(s)", len(response.output))
        for idx, transcript in enumerate(response.output):
            logger.info(
                "  Transcript %d: source length=%d, nBestTokens=%s",
                idx + 1,
                len(transcript.source),
                transcript.nBestTokens is not None,
            )
            if transcript.source:
                preview = transcript.source[:100]
                logger.debug(
                    "  Transcript %d text: %s%s",
                    idx + 1,
                    preview,
                    "..." if len(transcript.source) > 100 else "",
                )

        return response

    except InvalidLanguageCodeError as e:
        logger.warning("Language validation error in ASR inference: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ValueError as e:
        logger.warning("Validation error in ASR inference: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # Log full traceback for debugging and observability
        logger.error("ASR inference failed: %s", e, exc_info=True)

        # Import service-specific exceptions lazily to avoid circular imports
        from middleware.exceptions import (
            TritonInferenceError,
            ModelNotFoundError,
            ServiceUnavailableError,
            AudioProcessingError,
        )

        # If it's already a service-specific error, just re-raise
        if isinstance(
            e,
            (
                TritonInferenceError,
                ModelNotFoundError,
                ServiceUnavailableError,
                AudioProcessingError,
            ),
        ):
            raise

        error_msg = str(e)
        lower_msg = error_msg.lower()

        # Model not found in Triton
        if "unknown model" in lower_msg or ("model" in lower_msg and "not found" in lower_msg):
            import re

            model_match = re.search(r"model: '([^']+)'", error_msg)
            model_name = (
                model_match.group(1)
                if model_match
                else getattr(getattr(request, "config", None), "serviceId", "asr")
            )
            raise ModelNotFoundError(
                message=(
                    f"Model '{model_name}' not found in Triton inference server. "
                    f"Please verify the model name and ensure it is loaded."
                ),
                model_name=model_name,
            )

        # Triton / connectivity / timeout errors
        if "triton" in lower_msg or "connection" in lower_msg or "timeout" in lower_msg:
            raise ServiceUnavailableError(
                message=f"ASR service unavailable: {error_msg}. Please check Triton server connectivity.",
                service_name="asr",
            )

        # Audio processing errors
        if "audio" in lower_msg:
            raise AudioProcessingError(f"Audio processing failed: {error_msg}")

        # Generic Triton / inference error
        model_name = getattr(getattr(request, "config", None), "serviceId", "asr")
        raise TritonInferenceError(
            message=f"ASR inference failed: {error_msg}",
            model_name=model_name,
        )


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available ASR models",
    description="Get list of supported ASR models and languages"
)
async def list_models() -> Dict[str, Any]:
    """List available ASR models."""
    return {
        "models": [
            {
                "model_id": "vakyansh-asr-en",
                "languages": ["en"],
                "description": "English ASR model"
            },
            {
                "model_id": "conformer-asr-multilingual",
                "languages": ["hi", "ta", "te", "kn", "ml"],
                "description": "Multilingual ASR model for Indic languages"
            },
            {
                "model_id": "whisper-large-v3",
                "languages": ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa"],
                "description": "Whisper large v3 multilingual model"
            }
        ],
        "supported_languages": [
            "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
            "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai",
            "brx", "mni"
        ],
        "supported_formats": ["wav", "mp3", "flac", "ogg", "pcm"],
        "transcription_formats": ["transcript", "srt", "webvtt"]
    }


async def validate_request(request: ASRInferenceRequest) -> None:
    """Validate ASR inference request."""
    try:
        # Validate service ID
        validate_service_id(request.config.serviceId)
        
        # Validate language code
        validate_language_code(request.config.language.sourceLanguage)
        
        # Validate audio inputs
        for audio_input in request.audio:
            validate_audio_input(audio_input)
        
        # Validate preprocessors
        if request.config.preProcessors:
            validate_preprocessors(request.config.preProcessors)
        
        # Validate postprocessors
        if request.config.postProcessors:
            validate_postprocessors(request.config.postProcessors)
        
        # Validate best token count
        if request.config.bestTokenCount < 0 or request.config.bestTokenCount > 10:
            raise ValueError("bestTokenCount must be between 0 and 10")
        
    except Exception as e:
        logger.warning(f"Request validation failed: {e}")
        raise ValueError(f"Invalid request: {e}")
