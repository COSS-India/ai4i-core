"""
FastAPI router for TTS inference endpoints.
"""

import logging
import time
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.tts_request import TTSInferenceRequest
from models.tts_response import TTSInferenceResponse
from repositories.tts_repository import TTSRepository, get_db_session
from services.tts_service import TTSService
from services.audio_service import AudioService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.validation_utils import (
    validate_language_code,
    validate_service_id,
    validate_gender,
    validate_audio_format,
    validate_sample_rate,
    validate_text_input,
    validate_audio_duration
)
from middleware.exceptions import AuthenticationError, AuthorizationError

# Import OpenTelemetry for manual span creation
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

logger = logging.getLogger(__name__)

# Create router
# Authentication is handled by Kong + Auth Service, no need for AuthProvider here
inference_router = APIRouter(
    prefix="/api/v1/tts", 
    tags=["TTS Inference"]
)


async def get_tts_service(db: AsyncSession = Depends(get_db_session)) -> TTSService:
    """Dependency to get configured TTS service."""
    try:
        # Create repository
        repository = TTSRepository(db)
        
        # Create services
        audio_service = AudioService()
        text_service = TextService()
        
        # Create Triton client
        import os
        triton_url = os.getenv("TRITON_ENDPOINT", "http://localhost:8000")
        # Strip http:// or https:// scheme from URL (like ASR service)
        if triton_url.startswith(('http://', 'https://')):
            triton_url = triton_url.split('://', 1)[1]
        triton_api_key = os.getenv("TRITON_API_KEY")
        triton_client = TritonClient(triton_url, triton_api_key)
        
        # Create TTS service
        tts_service = TTSService(repository, audio_service, text_service, triton_client)
        
        return tts_service
        
    except Exception as e:
        logger.error(f"Failed to create TTS service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize TTS service"
        )


@inference_router.post(
    "/inference",
    response_model=TTSInferenceResponse,
    summary="Perform batch TTS inference",
    description="Convert text to speech for one or more text inputs"
)
async def run_inference(
    request: TTSInferenceRequest,
    http_request: Request,
    tts_service: TTSService = Depends(get_tts_service)
) -> TTSInferenceResponse:
    """Run TTS inference on text inputs."""
    start_time = time.time()
    request_id = None
    
    # Create a descriptive span for TTS inference
    if TRACING_AVAILABLE:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("TTS Inference") as span:
            span.set_attribute("service.name", "tts")
            span.set_attribute("service.type", "tts")
            span.set_attribute("tts.input_count", len(request.input))
            span.set_attribute("tts.service_id", request.config.serviceId)
            span.set_attribute("tts.language", request.config.language.sourceLanguage)
            span.set_attribute("tts.gender", request.config.gender.value)
            span.set_attribute("tts.audio_format", request.config.audioFormat.value)
            return await _run_tts_inference_internal(request, http_request, tts_service, start_time)
    else:
        return await _run_tts_inference_internal(request, http_request, tts_service, start_time)


async def _run_tts_inference_internal(request: TTSInferenceRequest, http_request: Request, tts_service: TTSService, start_time: float) -> TTSInferenceResponse:
    """Internal TTS inference logic."""
    try:
        # Extract auth context from request.state
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_id = getattr(http_request.state, 'api_key_id', None)
        session_id = getattr(http_request.state, 'session_id', None)
        
        # Validate request
        await validate_request(request)
        
        # Log request
        logger.info(f"Processing TTS inference request with {len(request.input)} text inputs - user_id={user_id} api_key_id={api_key_id}")
        
        response = await tts_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        
        # Log completion
        processing_time = time.time() - start_time
        logger.info(f"TTS inference completed in {processing_time:.2f}s")
        
        return response
        
    except ValueError as e:
        logger.warning(f"Validation error in TTS inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"TTS inference failed: {e}", exc_info=True)
        
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
            model_name = model_match.group(1) if model_match else "tts"
            raise ModelNotFoundError(
                message=f"Model '{model_name}' not found in Triton inference server. Please verify the model name and ensure it is loaded.",
                model_name=model_name
            )
        elif "triton" in error_msg.lower() or "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            raise ServiceUnavailableError(
                message=f"TTS service unavailable: {error_msg}. Please check Triton server connectivity."
            )
        elif "audio" in error_msg.lower():
            raise AudioProcessingError(f"Audio processing failed: {error_msg}")
        else:
            # Generic Triton error
            raise TritonInferenceError(
                message=f"TTS inference failed: {error_msg}",
                model_name="tts"
            )


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available TTS models",
    description="Get list of supported TTS models, languages, and voices"
)
async def list_models() -> Dict[str, Any]:
    """List available TTS models."""
    return {
        "models": [
            {
                "model_id": "indic-tts-coqui-dravidian",
                "languages": ["kn", "ml", "ta", "te"],
                "voices": ["male", "female"],
                "description": "Dravidian language TTS model"
            },
            {
                "model_id": "indic-tts-coqui-indo_aryan",
                "languages": ["hi", "bn", "gu", "mr", "pa"],
                "voices": ["male", "female"],
                "description": "Indo-Aryan language TTS model"
            },
            {
                "model_id": "indic-tts-coqui-misc",
                "languages": ["en", "brx", "mni"],
                "voices": ["male", "female"],
                "description": "Miscellaneous language TTS model"
            }
        ],
        "supported_languages": [
            "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
            "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai",
            "brx", "mni"
        ],
        "supported_voices": ["male", "female"],
        "supported_formats": ["wav", "mp3", "ogg", "pcm"],
        "supported_sample_rates": [8000, 16000, 22050, 44100, 48000]
    }


async def validate_request(request: TTSInferenceRequest) -> None:
    """Validate TTS inference request."""
    try:
        # Validate service ID
        validate_service_id(request.config.serviceId)
        
        # Validate language code
        validate_language_code(request.config.language.sourceLanguage)
        
        # Validate gender
        validate_gender(request.config.gender.value)
        
        # Validate audio format
        validate_audio_format(request.config.audioFormat.value)
        
        # Validate sample rate
        if request.config.samplingRate:
            validate_sample_rate(request.config.samplingRate)
        
        # Validate text inputs
        for text_input in request.input:
            validate_text_input(text_input.source)
            
            # Validate audio duration if specified
            if text_input.audioDuration:
                validate_audio_duration(text_input.audioDuration)
        
    except Exception as e:
        logger.warning(f"Request validation failed: {e}")
        raise ValueError(f"Invalid request: {e}")
