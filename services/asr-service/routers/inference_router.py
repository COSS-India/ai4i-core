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
    InvalidLanguageCodeError,
    InvalidServiceIdError,
    InvalidAudioInputError,
    InvalidPreprocessorError,
    InvalidPostprocessorError,
    NoFileSelectedError,
    UnsupportedFormatError,
    FileTooLargeError,
    InvalidFileError,
    UploadFailedError,
    AudioTooShortError,
    AudioTooLongError,
    EmptyAudioFileError,
    UploadTimeoutError
)
from middleware.exceptions import AuthenticationError, AuthorizationError, ErrorDetail
from middleware.auth_provider import AuthProvider
from services.constants.error_messages import (
    LANGUAGE_NOT_SUPPORTED,
    LANGUAGE_NOT_SUPPORTED_MESSAGE,
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_MESSAGE,
    MODEL_UNAVAILABLE,
    MODEL_UNAVAILABLE_MESSAGE,
    POOR_AUDIO_QUALITY,
    POOR_AUDIO_QUALITY_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_MESSAGE,
    PROCESSING_TIMEOUT,
    PROCESSING_TIMEOUT_MESSAGE,
    NO_FILE_SELECTED,
    NO_FILE_SELECTED_MESSAGE,
    UNSUPPORTED_FORMAT,
    UNSUPPORTED_FORMAT_MESSAGE,
    FILE_TOO_LARGE,
    FILE_TOO_LARGE_MESSAGE,
    INVALID_FILE,
    INVALID_FILE_MESSAGE,
    UPLOAD_FAILED,
    UPLOAD_FAILED_MESSAGE,
    AUDIO_TOO_SHORT,
    AUDIO_TOO_SHORT_MESSAGE,
    AUDIO_TOO_LONG,
    AUDIO_TOO_LONG_MESSAGE,
    EMPTY_AUDIO_FILE,
    EMPTY_AUDIO_FILE_MESSAGE,
    UPLOAD_TIMEOUT,
    UPLOAD_TIMEOUT_MESSAGE
)

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
            # Model Management failed to resolve endpoint for a specific serviceId
            logger.error(
                "Model Management did not resolve serviceId: %s and no default endpoint is allowed. Error: %s",
                service_id,
                model_mgmt_error,
            )
            error_detail = ErrorDetail(
                message=MODEL_UNAVAILABLE_MESSAGE,
                code=MODEL_UNAVAILABLE,
            )
            raise HTTPException(
                status_code=500,
                detail=error_detail.dict(),
            )
        else:
            # Request is missing required serviceId
            error_detail = ErrorDetail(
                message=INVALID_REQUEST_MESSAGE,
                code=INVALID_REQUEST,
            )
            raise HTTPException(
                status_code=400,
                detail=error_detail.dict(),
            )
    
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        error_detail = ErrorDetail(
            message=MODEL_UNAVAILABLE_MESSAGE,
            code=MODEL_UNAVAILABLE
        )
        logger.error(f"Model Management failed to resolve Triton model name for serviceId: {service_id}. Error: {model_mgmt_error}")
        raise HTTPException(
            status_code=500,
            detail=error_detail.dict(),
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
    # This will be a child of the FastAPI auto-instrumented span
    if TRACING_AVAILABLE:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("asr.inference") as span:
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
    # Check if Model Management resolved the service (dependency should have raised if not)
    triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
    triton_model_name = getattr(http_request.state, "triton_model_name", None)
    
    if not triton_endpoint or not triton_model_name:
        service_id = getattr(http_request.state, "service_id", None)
        error_detail = ErrorDetail(
            message=MODEL_UNAVAILABLE_MESSAGE,
            code=MODEL_UNAVAILABLE
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail.dict(),
        )
    
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
        logger.warning(f"Language validation error in ASR inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=LANGUAGE_NOT_SUPPORTED, message=LANGUAGE_NOT_SUPPORTED_MESSAGE).dict()
        )
    except (NoFileSelectedError, UnsupportedFormatError, FileTooLargeError, 
            InvalidFileError, UploadFailedError, AudioTooShortError, 
            AudioTooLongError, EmptyAudioFileError, UploadTimeoutError) as e:
        # Map specific file validation errors to their error codes
        error_code_map = {
            NoFileSelectedError: NO_FILE_SELECTED,
            UnsupportedFormatError: UNSUPPORTED_FORMAT,
            FileTooLargeError: FILE_TOO_LARGE,
            InvalidFileError: INVALID_FILE,
            UploadFailedError: UPLOAD_FAILED,
            AudioTooShortError: AUDIO_TOO_SHORT,
            AudioTooLongError: AUDIO_TOO_LONG,
            EmptyAudioFileError: EMPTY_AUDIO_FILE,
            UploadTimeoutError: UPLOAD_TIMEOUT,
        }
        error_message_map = {
            NoFileSelectedError: NO_FILE_SELECTED_MESSAGE,
            UnsupportedFormatError: UNSUPPORTED_FORMAT_MESSAGE,
            FileTooLargeError: FILE_TOO_LARGE_MESSAGE,
            InvalidFileError: INVALID_FILE_MESSAGE,
            UploadFailedError: UPLOAD_FAILED_MESSAGE,
            AudioTooShortError: AUDIO_TOO_SHORT_MESSAGE,
            AudioTooLongError: AUDIO_TOO_LONG_MESSAGE,
            EmptyAudioFileError: EMPTY_AUDIO_FILE_MESSAGE,
            UploadTimeoutError: UPLOAD_TIMEOUT_MESSAGE,
        }
        error_type = type(e)
        error_code = error_code_map.get(error_type, INVALID_REQUEST)
        error_message = error_message_map.get(error_type, str(e))
        logger.warning(f"File validation error in ASR inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=error_code, message=error_message).dict()
        )
    except ValueError as e:
        logger.warning(f"Validation error in ASR inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorDetail(code=INVALID_REQUEST, message=INVALID_REQUEST_MESSAGE).dict()
        )
    except Exception as e:
        logger.error(f"ASR inference failed: {e}", exc_info=True)
        
        # Extract context from request state for better error messages
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        model_name = getattr(http_request.state, "triton_model_name", None)
        
        # Return appropriate error based on exception type
        if "Triton" in str(e) or "triton" in str(e).lower():
            error_detail = f"Triton inference failed for serviceId '{service_id}'"
            if triton_endpoint and model_name:
                error_detail += f" at endpoint '{triton_endpoint}' with model '{model_name}': {str(e)}. "
                error_detail += "Please verify the model is registered in Model Management and the Triton server is accessible."
            elif service_id:
                error_detail += f": {str(e)}. Please verify the service is registered in Model Management."
            else:
                error_detail += f": {str(e)}"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_detail
            )
        elif "audio" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Audio processing failed: {str(e)}"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal server error: {str(e)}"
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
        
    except (InvalidLanguageCodeError, InvalidServiceIdError, InvalidAudioInputError, 
            InvalidPreprocessorError, InvalidPostprocessorError, NoFileSelectedError,
            UnsupportedFormatError, FileTooLargeError, InvalidFileError, UploadFailedError,
            AudioTooShortError, AudioTooLongError, EmptyAudioFileError, UploadTimeoutError):
        # Re-raise specific validation errors as-is so they get proper error codes
        raise
    except Exception as e:
        logger.warning(f"Request validation failed: {e}")
        raise ValueError(f"Invalid request: {e}")
