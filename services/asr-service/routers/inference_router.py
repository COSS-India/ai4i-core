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
    validate_postprocessors
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


async def get_asr_service(db: AsyncSession = Depends(get_db_session)) -> ASRService:
    """Dependency to get configured ASR service."""
    try:
        # Create repository
        repository = ASRRepository(db)
        
        # Create audio service
        audio_service = AudioService()
        
        # Create Triton client
        import os
        triton_url = os.getenv("TRITON_ENDPOINT", "http://localhost:8000")
        # Strip http:// or https:// scheme from URL
        if triton_url.startswith(('http://', 'https://')):
            triton_url = triton_url.split('://', 1)[1]
        triton_api_key = os.getenv("TRITON_API_KEY")
        triton_client = TritonClient(triton_url, triton_api_key)
        
        # Create ASR service
        asr_service = ASRService(repository, audio_service, triton_client)
        
        return asr_service
        
    except Exception as e:
        logger.error(f"Failed to create ASR service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize ASR service"
        )


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
        
        return response
        
    except ValueError as e:
        logger.warning(f"Validation error in ASR inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"ASR inference failed: {e}", exc_info=True)
        
        # Import service-specific exceptions
        from middleware.exceptions import (
            TritonInferenceError,
            ModelNotFoundError,
            ServiceUnavailableError,
            AudioProcessingError
        )
        
        # Check if it's already a service-specific error
        if isinstance(e, (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError, AudioProcessingError)):
            raise
        
        # Check error type and raise appropriate exception
        error_msg = str(e)
        if "unknown model" in error_msg.lower() or ("model" in error_msg.lower() and "not found" in error_msg.lower()):
            import re
            model_match = re.search(r"model: '([^']+)'", error_msg)
            model_name = model_match.group(1) if model_match else request.config.serviceId if hasattr(request, 'config') else "asr"
            raise ModelNotFoundError(
                message=f"Model '{model_name}' not found in Triton inference server. Please verify the model name and ensure it is loaded.",
                model_name=model_name
            )
        elif "triton" in error_msg.lower() or "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            raise ServiceUnavailableError(
                message=f"ASR service unavailable: {error_msg}. Please check Triton server connectivity."
            )
        elif "audio" in error_msg.lower():
            raise AudioProcessingError(f"Audio processing failed: {error_msg}")
        else:
            # Generic Triton error
            model_name = request.config.serviceId if hasattr(request, 'config') and hasattr(request.config, 'serviceId') else "asr"
            raise TritonInferenceError(
                message=f"ASR inference failed: {error_msg}",
                model_name=model_name
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
