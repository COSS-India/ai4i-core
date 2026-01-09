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
from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError,
    ServiceUnavailableError,
    AudioProcessingError
)
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
    
    # Check if Model Management resolved the service (dependency should have raised if not)
    triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
    triton_model_name = getattr(http_request.state, "triton_model_name", None)
    
    if not triton_endpoint or not triton_model_name:
        service_id = getattr(http_request.state, "service_id", None)
        raise HTTPException(
            status_code=500,
            detail=(
                f"Model Management failed to resolve service. "
                f"serviceId: {service_id}, endpoint: {triton_endpoint}, model_name: {triton_model_name}"
            ),
        )
    
    # Create a descriptive span for ASR inference
    if TRACING_AVAILABLE:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("ASR Inference") as span:
            span.set_attribute("service.name", "asr")
            span.set_attribute("service.type", "asr")
            span.set_attribute("asr.audio_count", len(request.audio))
            span.set_attribute("asr.service_id", request.config.serviceId)
            span.set_attribute("asr.language", request.config.language.sourceLanguage)
            return await _run_asr_inference_internal(request, http_request, asr_service, start_time)
    else:
        return await _run_asr_inference_internal(request, http_request, asr_service, start_time)


async def _run_asr_inference_internal(request: ASRInferenceRequest, http_request: Request, asr_service: ASRService, start_time: float) -> ASRInferenceResponse:
    """Internal ASR inference logic."""
    try:
        # Extract auth context from request.state
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_id = getattr(http_request.state, 'api_key_id', None)
        session_id = getattr(http_request.state, 'session_id', None)
        
        # Validate request
        await validate_request(request)
        
        # Log request
        logger.info(f"Processing ASR inference request with {len(request.audio)} audio inputs - user_id={user_id} api_key_id={api_key_id}")
        
        # Run inference with auth context
        response = await asr_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        
        # Log completion
        processing_time = time.time() - start_time
        logger.info(f"ASR inference completed in {processing_time:.2f}s")
        
        # Debug: Log response structure
        logger.info(f"Response contains {len(response.output)} transcript(s)")
        for idx, transcript in enumerate(response.output):
            logger.info(f"  Transcript {idx + 1}: source length={len(transcript.source)}, nBestTokens={transcript.nBestTokens is not None}")
            logger.debug(f"  Transcript {idx + 1} text: {transcript.source[:100]}{'...' if len(transcript.source) > 100 else ''}")
        
        return response
        
    except InvalidLanguageCodeError as e:
        logger.warning(f"Language validation error in ASR inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ValueError as e:
        logger.warning(f"Validation error in ASR inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"ASR inference failed: {e}", exc_info=True, exc_info=True)
        
        # Extract context from request state for better error messages
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        model_name = getattr(http_request.state, "triton_model_name", None)
        
        # Return appropriate error based on exception type
        error_msg = str(e)
        if "Triton" in error_msg or "triton" in error_msg.lower():
            if "404" in error_msg or "Not Found" in error_msg or "unknown model" in error_msg.lower():
                from middleware.exceptions import ModelNotFoundError
                raise ModelNotFoundError(
                    message=f"Triton model not found. Please verify the model name and ensure it is loaded.",
                    model_name=model_name or "unknown"
                )
            elif "connection" in error_msg.lower() or "connect" in error_msg.lower() or "timeout" in error_msg.lower():
                raise ServiceUnavailableError(
                    message=f"ASR service unavailable: {error_msg}. Please check Triton server connectivity.",
                    service_name="triton"
                )
            else:
                from middleware.exceptions import TritonInferenceError
                raise TritonInferenceError(
                    message=f"Triton inference failed: {error_msg}",
                    model_name=model_name
                )
        elif "audio" in error_msg.lower():
            raise AudioProcessingError(f"Audio processing failed: {error_msg}")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal server error: {error_msg}"
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
