"""
FastAPI router for TTS inference endpoints.
"""

import logging
import time
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id

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

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("tts-service")

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
    """
    Run TTS inference on text inputs.
    
    Creates detailed trace spans for the entire inference operation.
    """
    # Create a span for the entire inference operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _run_tts_inference_impl(request, http_request, tts_service)
    
    with tracer.start_as_current_span("tts.inference") as span:
        try:
            # Extract auth context from request.state (if middleware is configured)
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            session_id = getattr(http_request.state, "session_id", None)
            
            # Get correlation ID for log/trace correlation
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)

            # Add request metadata to span
            span.set_attribute("tts.input_count", len(request.input))
            span.set_attribute("tts.service_id", request.config.serviceId)
            span.set_attribute("tts.language", request.config.language.sourceLanguage)
            span.set_attribute("tts.gender", request.config.gender.value)
            span.set_attribute("tts.audio_format", request.config.audioFormat.value)
            span.set_attribute("tts.sampling_rate", request.config.samplingRate or 22050)
            
            # Track request size (approximate)
            try:
                import json
                request_size = len(json.dumps(request.dict()).encode('utf-8'))
                span.set_attribute("http.request.size_bytes", request_size)
            except Exception:
                pass
            
            if user_id:
                span.set_attribute("user.id", str(user_id))
            if api_key_id:
                span.set_attribute("api_key.id", str(api_key_id))
            if session_id:
                span.set_attribute("session.id", str(session_id))
            
            # Add span event for request start
            span.add_event("tts.inference.started", {
                "input_count": len(request.input),
                "service_id": request.config.serviceId,
                "language": request.config.language.sourceLanguage
            })

            logger.info(
                "Processing TTS inference request with %d text input(s), user_id=%s api_key_id=%s session_id=%s",
                len(request.input),
                user_id,
                api_key_id,
                session_id,
            )

            # Run inference
            response = await tts_service.run_inference(
                request=request,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            
            # Add response metadata
            span.set_attribute("tts.output_count", len(response.audio))
            span.set_attribute("http.status_code", 200)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("tts.inference.completed", {
                "output_count": len(response.audio),
                "status": "success"
            })
            span.set_status(Status(StatusCode.OK))
            logger.info("TTS inference completed successfully")
            return response

        except ValueError as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", "ValueError")
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("tts.inference.failed", {
                "error_type": "ValueError",
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Validation error in TTS inference: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            # Import service-specific exceptions
            from middleware.exceptions import (
                TritonInferenceError,
                ModelNotFoundError,
                ServiceUnavailableError,
                AudioProcessingError
            )
            
            # Check if it's already a service-specific error
            if isinstance(exc, (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError, AudioProcessingError)):
                error_type = type(exc).__name__
                status_code = getattr(exc, 'status_code', 500)
            else:
                # Check error type and determine status code
                error_msg = str(exc)
                error_type = type(exc).__name__
                if "unknown model" in error_msg.lower() or ("model" in error_msg.lower() and "not found" in error_msg.lower()):
                    error_type = "ModelNotFoundError"
                    status_code = 404
                elif "triton" in error_msg.lower() or "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                    error_type = "ServiceUnavailableError"
                    status_code = 503
                elif "audio" in error_msg.lower():
                    error_type = "AudioProcessingError"
                    status_code = 500
                else:
                    status_code = 500
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", error_type)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", status_code)
            span.add_event("tts.inference.failed", {
                "error_type": error_type,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.error("TTS inference failed: %s", exc, exc_info=True)
            
            # Re-raise the exception (error_handler_middleware will handle it)
            raise


async def _run_tts_inference_impl(
    request: TTSInferenceRequest,
    http_request: Request,
    tts_service: TTSService,
) -> TTSInferenceResponse:
    """Fallback implementation when tracing is not available."""
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    # Validate request
    await validate_request(request)

    logger.info(
        "Processing TTS inference request with %d text input(s), user_id=%s api_key_id=%s session_id=%s",
        len(request.input),
        user_id,
        api_key_id,
        session_id,
    )

    response = await tts_service.run_inference(
        request=request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id
    )
    logger.info("TTS inference completed successfully")
    return response


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
