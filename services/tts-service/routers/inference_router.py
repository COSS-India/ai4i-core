"""
FastAPI router for TTS inference endpoints.
"""

import logging
import time
import traceback
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.tts_request import TTSInferenceRequest
from models.tts_response import TTSInferenceResponse
from repositories.tts_repository import TTSRepository
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
    validate_audio_duration,
    InvalidLanguageCodeError,
    InvalidServiceIdError,
    InvalidGenderError,
    InvalidAudioFormatError,
    InvalidSampleRateError,
    NoTextInputError,
    TextTooShortError,
    TextTooLongError,
    InvalidCharactersError,
    EmptyInputError,
    LanguageMismatchError,
    VoiceNotAvailableError
)
from middleware.exceptions import AuthenticationError, AuthorizationError, ErrorDetail
from services.constants.error_messages import (
    NO_TEXT_INPUT,
    NO_TEXT_INPUT_MESSAGE,
    TEXT_TOO_SHORT,
    TEXT_TOO_SHORT_MESSAGE,
    TEXT_TOO_LONG,
    TEXT_TOO_LONG_MESSAGE,
    INVALID_CHARACTERS,
    INVALID_CHARACTERS_MESSAGE,
    EMPTY_INPUT,
    EMPTY_INPUT_MESSAGE,
    LANGUAGE_MISMATCH,
    LANGUAGE_MISMATCH_MESSAGE,
    LANGUAGE_NOT_SUPPORTED,
    LANGUAGE_NOT_SUPPORTED_TTS_MESSAGE,
    VOICE_NOT_AVAILABLE,
    VOICE_NOT_AVAILABLE_MESSAGE,
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_TTS_MESSAGE,
    PROCESSING_FAILED,
    PROCESSING_FAILED_MESSAGE,
    MODEL_UNAVAILABLE,
    MODEL_UNAVAILABLE_TTS_MESSAGE,
    AUDIO_GEN_FAILED,
    AUDIO_GEN_FAILED_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_TTS_MESSAGE,
    INTERNAL_SERVER_ERROR,
    INTERNAL_SERVER_ERROR_MESSAGE
)
from middleware.exceptions import AuthenticationError, AuthorizationError
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id

logger = logging.getLogger(__name__)


def count_words(text: str) -> int:
    """Count words in text"""
    try:
        words = [word for word in text.split() if word.strip()]
        return len(words)
    except Exception:
        return 0
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("tts-service")

# Create router
# Enforce auth and permission checks on all routes (same as OCR and NMT)
inference_router = APIRouter(
    prefix="/api/v1/tts", 
    tags=["TTS Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_tts_service(request: Request, db: AsyncSession = Depends(get_tenant_db_session)) -> TTSService:
    """Dependency to get configured TTS service. Uses request.state from Model Management middleware when set (e.g. A/B variant)."""
    try:
        # Create repository
        repository = TTSRepository(db)
        
        # Create services
        audio_service = AudioService()
        text_service = TextService()
        
        # Triton endpoint: prefer middleware-resolved (A/B variant or service resolution)
        import os
        triton_endpoint = getattr(request.state, "triton_endpoint", None)
        triton_api_key = getattr(request.state, "triton_api_key", None)
        if not triton_endpoint:
            triton_url = os.getenv("TRITON_ENDPOINT", "http://localhost:8000")
            if triton_url.startswith(('http://', 'https://')):
                triton_url = triton_url.split('://', 1)[1]
            triton_endpoint = triton_url
            if triton_api_key is None:
                triton_api_key = os.getenv("TRITON_API_KEY")
        triton_client = TritonClient(triton_endpoint, triton_api_key)
        
        # Create TTS service
        tts_service = TTSService(repository, audio_service, text_service, triton_client)
        
        return tts_service
        
    except Exception as e:
        # Extract context for logging (if available from request)
        # get_correlation_id is already imported at top of file
        correlation_id = None
        user_id = None
        api_key_id = None
        try:
            # Try to get request from context if available
            from starlette.requests import Request
            request = getattr(db, 'request', None) if hasattr(db, 'request') else None
            if request:
                correlation_id = get_correlation_id(request) or getattr(request.state, "correlation_id", None)
                user_id = getattr(request.state, "user_id", None)
                api_key_id = getattr(request.state, "api_key_id", None)
        except Exception:
            pass
        
        # Trace the error if we're in a span context
        try:
            from opentelemetry import trace
            from opentelemetry.trace import Status, StatusCode
            if trace:
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", type(e).__name__)
                    current_span.set_attribute("error.message", str(e))
                    current_span.set_attribute("http.status_code", 500)
                    current_span.set_status(Status(StatusCode.ERROR, str(e)))
                    current_span.record_exception(e)
                    if correlation_id:
                        current_span.set_attribute("correlation.id", correlation_id)
        except Exception:
            pass  # Don't fail if tracing fails
        
        logger.error(
            f"Failed to create TTS service: {e}",
            extra={
                "context": {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "status_code": 500,
                    "user_id": user_id,
                    "api_key_id": api_key_id,
                    "correlation_id": correlation_id,
                }
            },
            exc_info=True
        )
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
    Run TTS inference on the given request.
    
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
            if request.config.samplingRate:
                span.set_attribute("tts.sampling_rate", request.config.samplingRate)
            
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
                "language": request.config.language.sourceLanguage,
                "gender": request.config.gender.value
            })

            # Calculate input metrics (character length and word count)
            input_texts = [text_input.source for text_input in request.input]
            total_input_characters = sum(len(text) for text in input_texts)
            total_input_words = sum(count_words(text) for text in input_texts)
            
            # Store input details in request.state for middleware to access
            http_request.state.input_details = {
                "character_length": total_input_characters,
                "word_count": total_input_words,
                "input_count": len(request.input)
            }
            
            logger.info(
                "Processing TTS inference request with %d text input(s), input_characters=%d, input_words=%d, user_id=%s api_key_id=%s session_id=%s",
                len(request.input),
                total_input_characters,
                total_input_words,
                user_id,
                api_key_id,
                session_id,
                extra={
                    # Common input/output details structure (general fields for all services)
                    "input_details": {
                        "character_length": total_input_characters,
                        "word_count": total_input_words,
                        "input_count": len(request.input)
                    },
                    # Service metadata (for filtering)
                    "service_id": request.config.serviceId,
                    "source_language": request.config.language.sourceLanguage,
                }
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
            
            # Calculate output metrics (audio duration) for successful responses
            total_output_audio_duration = 0.0
            total_output_audio_size = 0
            if response.audio:
                import base64
                for audio_output in response.audio:
                    try:
                        audio_bytes = base64.b64decode(audio_output.audioContent)
                        total_output_audio_size += len(audio_bytes)
                        # Estimate duration: assume 2 bytes per sample for 16-bit audio at target sample rate
                        target_sr = request.config.samplingRate or 22050
                        total_samples = len(audio_bytes) / 2
                        total_output_audio_duration += total_samples / target_sr
                    except Exception:
                        pass
            
            # Store output details in request.state for middleware to access
            http_request.state.output_details = {
                "audio_length_seconds": total_output_audio_duration,
                "audio_length_ms": total_output_audio_duration * 1000.0,
                "output_count": len(response.audio)
            }
            
            # Add output audio length to trace span
            span.set_attribute("tts.output.audio_length_seconds", total_output_audio_duration)
            span.set_attribute("tts.output.audio_length_ms", total_output_audio_duration * 1000.0)
            if total_output_audio_size > 0:
                span.set_attribute("tts.output.audio_size_bytes", total_output_audio_size)
            
            # Add span event for successful completion
            span.add_event("tts.inference.completed", {
                "output_count": len(response.audio),
                "output_audio_duration": total_output_audio_duration,
                "output_audio_length_seconds": total_output_audio_duration,
                "status": "success"
            })
            span.set_status(Status(StatusCode.OK))
            logger.info(
                "TTS inference completed successfully, output_audio_duration=%.2fs",
                total_output_audio_duration,
                extra={
                    # Common input/output details structure (general fields for all services)
                    "input_details": {
                        "character_length": total_input_characters,
                        "word_count": total_input_words,
                        "input_count": len(request.input)
                    },
                    "output_details": {
                        "audio_length_seconds": total_output_audio_duration,
                        "audio_length_ms": total_output_audio_duration * 1000.0,
                        "output_count": len(response.audio)
                    },
                    # Service metadata (for filtering)
                    "service_id": request.config.serviceId,
                    "source_language": request.config.language.sourceLanguage,
                    "http_status_code": 200,
                }
            )
            return response

        except ValueError as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("tts.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Validation error in TTS inference: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc)
            ) from exc

        except Exception as exc:
            # Extract context for logging
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            session_id = getattr(http_request.state, "session_id", None)
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            # Get correlation ID for logging (already imported at top of file)
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            
            # Trace the error
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", getattr(exc, 'status_code', 500))
            if service_id:
                span.set_attribute("tts.service_id", service_id)
            if triton_endpoint:
                span.set_attribute("triton.endpoint", triton_endpoint)
            if model_name:
                span.set_attribute("triton.model_name", model_name)
            span.add_event("tts.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            
            # Log error with full context
            logger.error(
                f"TTS inference failed: {exc}",
                extra={
                    "context": {
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "service_id": service_id,
                        "triton_endpoint": triton_endpoint,
                        "model_name": model_name,
                        "user_id": user_id,
                        "api_key_id": api_key_id,
                        "session_id": session_id,
                        "correlation_id": correlation_id,
                        "input_count": len(request.input) if hasattr(request, 'input') else None,
                    }
                },
                exc_info=True
            )
            
            # Import service-specific exceptions
            from middleware.exceptions import (
                TritonInferenceError,
                ModelNotFoundError,
                ServiceUnavailableError,
                AudioProcessingError
            )
            
            # Check if it's already a service-specific error
            if isinstance(exc, (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError, AudioProcessingError)):
                raise
            
            # Check error type and raise appropriate exception
            error_msg = str(exc)
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


async def _run_tts_inference_impl(
    request: TTSInferenceRequest,
    http_request: Request,
    tts_service: TTSService,
) -> TTSInferenceResponse:
    """Fallback implementation when tracing is not available."""
    # Validate request
    await validate_request(request)
    
    # Extract auth context from request.state
    user_id = getattr(http_request.state, 'user_id', None)
    api_key_id = getattr(http_request.state, 'api_key_id', None)
    session_id = getattr(http_request.state, 'session_id', None)
    
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
        
    except (NoTextInputError, EmptyInputError, TextTooShortError, TextTooLongError, 
            InvalidCharactersError, LanguageMismatchError, InvalidLanguageCodeError,
            VoiceNotAvailableError, InvalidServiceIdError, InvalidGenderError,
            InvalidAudioFormatError, InvalidSampleRateError):
        # Re-raise specific validation exceptions directly (they will be caught by handlers above)
        raise
    except Exception as e:
        logger.warning(f"Request validation failed: {e}")
        raise ValueError(f"Invalid request: {e}")
