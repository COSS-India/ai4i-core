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
        
    except NoTextInputError:
        logger.warning("No text input provided in TTS inference")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=NO_TEXT_INPUT, message=NO_TEXT_INPUT_MESSAGE).dict()
        )
    except EmptyInputError:
        logger.warning("Empty text input in TTS inference")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=NO_TEXT_INPUT, message=NO_TEXT_INPUT_MESSAGE).dict()
        )
    except TextTooShortError:
        logger.warning("Text too short in TTS inference")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=TEXT_TOO_SHORT, message=TEXT_TOO_SHORT_MESSAGE).dict()
        )
    except TextTooLongError:
        logger.warning("Text too long in TTS inference")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=TEXT_TOO_LONG, message=TEXT_TOO_LONG_MESSAGE).dict()
        )
    except InvalidCharactersError:
        logger.warning("Invalid characters in TTS inference")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=INVALID_CHARACTERS, message=INVALID_CHARACTERS_MESSAGE).dict()
        )
    except LanguageMismatchError:
        logger.warning("Language mismatch in TTS inference")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=LANGUAGE_MISMATCH, message=LANGUAGE_MISMATCH_MESSAGE).dict()
        )
    except InvalidLanguageCodeError:
        logger.warning("Invalid language code in TTS inference")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=LANGUAGE_NOT_SUPPORTED, message=LANGUAGE_NOT_SUPPORTED_TTS_MESSAGE).dict()
        )
    except VoiceNotAvailableError:
        logger.warning("Voice not available in TTS inference")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=VOICE_NOT_AVAILABLE, message=VOICE_NOT_AVAILABLE_MESSAGE).dict()
        )
    except (InvalidServiceIdError, InvalidGenderError, InvalidAudioFormatError, InvalidSampleRateError) as e:
        logger.warning(f"Invalid request parameter in TTS inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=INVALID_REQUEST, message=INVALID_REQUEST_TTS_MESSAGE).dict()
        )
    except ValueError as e:
        logger.warning(f"Validation error in TTS inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=INVALID_REQUEST, message=INVALID_REQUEST_TTS_MESSAGE).dict()
        )
    except Exception as e:
        logger.error(f"TTS inference failed: {e}", exc_info=True)
        logger.error(f"Traceback: {traceback.format_exc()}")
        
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
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=ErrorDetail(code=MODEL_UNAVAILABLE, message=MODEL_UNAVAILABLE_TTS_MESSAGE).dict()
            )
        elif "triton" in error_msg.lower() or "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=ErrorDetail(code=SERVICE_UNAVAILABLE, message=SERVICE_UNAVAILABLE_TTS_MESSAGE).dict()
            )
        elif "audio" in error_msg.lower() or "generation" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorDetail(code=AUDIO_GEN_FAILED, message=AUDIO_GEN_FAILED_MESSAGE).dict()
            )
        elif "processing" in error_msg.lower() or "failed" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorDetail(code=PROCESSING_FAILED, message=PROCESSING_FAILED_MESSAGE).dict()
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorDetail(code=INTERNAL_SERVER_ERROR, message=str(e) if str(e) else INTERNAL_SERVER_ERROR_MESSAGE).dict()
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
        
    except (NoTextInputError, EmptyInputError, TextTooShortError, TextTooLongError, 
            InvalidCharactersError, LanguageMismatchError, InvalidLanguageCodeError,
            VoiceNotAvailableError, InvalidServiceIdError, InvalidGenderError,
            InvalidAudioFormatError, InvalidSampleRateError):
        # Re-raise specific validation exceptions directly (they will be caught by handlers above)
        raise
    except Exception as e:
        logger.warning(f"Request validation failed: {e}")
        raise ValueError(f"Invalid request: {e}")
