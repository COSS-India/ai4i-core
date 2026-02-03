"""
FastAPI router for ASR inference endpoints.
"""

import logging
import time
import base64
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.asr_request import ASRInferenceRequest
from models.asr_response import ASRInferenceResponse
from repositories.asr_repository import ASRRepository
from services.asr_service import ASRService
from services.audio_service import AudioService
from utils.triton_client import TritonClient
from utils.audio_utils import get_audio_duration
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
from middleware.tenant_db_dependency import get_tenant_db_session
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
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    trace = None
    Status = None
    StatusCode = None

logger = logging.getLogger(__name__)

# Create router with authentication dependency
inference_router = APIRouter(
    prefix="/api/v1/asr",
    tags=["ASR Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_asr_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session)
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
        
        # Extract context for logging
        from ai4icore_logging import get_correlation_id
        correlation_id = get_correlation_id(request) or getattr(request.state, "correlation_id", None)
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Trace the error if we're in a span context
        if TRACING_AVAILABLE and trace:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "ModelUnavailableError")
                    current_span.set_attribute("error.message", f"Model Management did not resolve serviceId: {service_id}")
                    current_span.set_attribute("http.status_code", 500)
                    current_span.set_status(Status(StatusCode.ERROR, f"Model Management did not resolve serviceId: {service_id}"))
                    if service_id:
                        current_span.set_attribute("asr.service_id", service_id)
                    if correlation_id:
                        current_span.set_attribute("correlation.id", correlation_id)
            except Exception:
                pass  # Don't fail if tracing fails
        
        if service_id:
            # Model Management failed to resolve endpoint for a specific serviceId
            logger.error(
                f"Model Management did not resolve serviceId: {service_id} and no default endpoint is allowed. Error: {model_mgmt_error}",
                extra={
                    "context": {
                        "error_type": "ModelUnavailableError",
                        "error_message": f"Model Management did not resolve serviceId: {service_id}",
                        "status_code": 500,
                        "service_id": service_id,
                        "model_management_error": model_mgmt_error,
                        "user_id": user_id,
                        "api_key_id": api_key_id,
                        "correlation_id": correlation_id,
                        "path": request.url.path,
                        "method": request.method,
                    }
                },
                exc_info=True
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
        
        # Extract context for logging
        from ai4icore_logging import get_correlation_id
        correlation_id = get_correlation_id(request) or getattr(request.state, "correlation_id", None)
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        triton_endpoint = getattr(request.state, "triton_endpoint", None)
        
        # Trace the error if we're in a span context
        if TRACING_AVAILABLE and trace:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "ModelUnavailableError")
                    current_span.set_attribute("error.message", f"Model Management failed to resolve Triton model name for serviceId: {service_id}")
                    current_span.set_attribute("http.status_code", 500)
                    current_span.set_status(Status(StatusCode.ERROR, f"Model Management failed to resolve Triton model name for serviceId: {service_id}"))
                    if service_id:
                        current_span.set_attribute("asr.service_id", service_id)
                    if triton_endpoint:
                        current_span.set_attribute("triton.endpoint", triton_endpoint)
                    if correlation_id:
                        current_span.set_attribute("correlation.id", correlation_id)
            except Exception:
                pass  # Don't fail if tracing fails
        
        error_detail = ErrorDetail(
            message=MODEL_UNAVAILABLE_MESSAGE,
            code=MODEL_UNAVAILABLE
        )
        logger.error(
            f"Model Management failed to resolve Triton model name for serviceId: {service_id}. Error: {model_mgmt_error}",
            extra={
                "context": {
                    "error_type": "ModelUnavailableError",
                    "error_message": f"Model Management failed to resolve Triton model name for serviceId: {service_id}",
                    "status_code": 500,
                    "service_id": service_id,
                    "triton_endpoint": triton_endpoint,
                    "model_management_error": model_mgmt_error,
                    "user_id": user_id,
                    "api_key_id": api_key_id,
                    "correlation_id": correlation_id,
                    "path": request.url.path,
                    "method": request.method,
                }
            },
            exc_info=True
        )
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
    if not TRACING_AVAILABLE:
        # Fallback if tracing not available
        return await _run_asr_inference_internal(request, http_request, asr_service, start_time)
    
    tracer = trace.get_tracer("asr-service")
    with tracer.start_as_current_span("asr.inference") as span:
        try:
            # Extract auth context from request.state (if middleware is configured)
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            session_id = getattr(http_request.state, "session_id", None)
            
            # Get correlation ID for log/trace correlation
            from ai4icore_logging import get_correlation_id
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)
            
            # Add request metadata to span
            span.set_attribute("service.name", "asr")
            span.set_attribute("service.type", "asr")
            span.set_attribute("asr.audio_count", len(request.audio))
            try:
                span.set_attribute("asr.service_id", request.config.serviceId)
                span.set_attribute("asr.language", request.config.language.sourceLanguage)
                if request.config.language.targetLanguage:
                    span.set_attribute("asr.target_language", request.config.language.targetLanguage)
            except Exception:
                # Config may be missing or malformed; don't fail tracing because of this
                pass
            
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
            span.add_event("asr.inference.started", {
                "audio_count": len(request.audio),
                "service_id": request.config.serviceId if request.config else "unknown"
            })
            
            return await _run_asr_inference_internal(request, http_request, asr_service, start_time)
            
        except Exception as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 500)
            span.add_event("asr.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


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
        
        # Extract context for logging
        from ai4icore_logging import get_correlation_id
        correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        
        # Trace the error if we're in a span context
        if TRACING_AVAILABLE and trace:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "ModelUnavailableError")
                    current_span.set_attribute("error.message", f"Triton endpoint or model name not resolved for serviceId: {service_id}")
                    current_span.set_attribute("http.status_code", 500)
                    current_span.set_status(Status(StatusCode.ERROR, f"Triton endpoint or model name not resolved for serviceId: {service_id}"))
                    if service_id:
                        current_span.set_attribute("asr.service_id", service_id)
                    if correlation_id:
                        current_span.set_attribute("correlation.id", correlation_id)
            except Exception:
                pass  # Don't fail if tracing fails
        
        error_detail = ErrorDetail(
            message=MODEL_UNAVAILABLE_MESSAGE,
            code=MODEL_UNAVAILABLE
        )
        logger.error(
            f"Triton endpoint or model name not resolved for serviceId: {service_id}",
            extra={
                "context": {
                    "error_type": "ModelUnavailableError",
                    "error_message": f"Triton endpoint or model name not resolved for serviceId: {service_id}",
                    "status_code": 500,
                    "service_id": service_id,
                    "triton_endpoint": triton_endpoint,
                    "triton_model_name": triton_model_name,
                    "user_id": user_id,
                    "api_key_id": api_key_id,
                    "correlation_id": correlation_id,
                    "path": http_request.url.path,
                    "method": http_request.method,
                }
            },
            exc_info=True
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
        
        # Calculate input metrics (audio duration)
        total_input_audio_duration = 0.0
        for audio_input in request.audio:
            duration = calculate_audio_duration(audio_input)
            total_input_audio_duration += duration
        
        # Store input details in request.state for middleware to access
        http_request.state.input_details = {
            "audio_length_seconds": total_input_audio_duration,
            "audio_length_ms": total_input_audio_duration * 1000.0,
            "input_count": len(request.audio)
        }
        
        # Log request
        logger.info(
            "Processing ASR inference request with %d audio inputs, audio_duration=%.2fs - user_id=%s api_key_id=%s",
            len(request.audio),
            total_input_audio_duration,
            user_id,
            api_key_id,
            extra={
                # Common input/output details structure (general fields for all services)
                "input_details": {
                    "audio_length_seconds": total_input_audio_duration,
                    "audio_length_ms": total_input_audio_duration * 1000.0,
                    "input_count": len(request.audio)
                },
                # Service metadata (for filtering)
                "service_id": request.config.serviceId if request.config else None,
                "source_language": request.config.language.sourceLanguage if request.config and request.config.language else None,
            }
        )
        
        # Run inference with auth context
        response = await asr_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
        )
        
        # Calculate output metrics (character length and word count) for successful responses
        output_texts = [output.source for output in response.output]
        total_output_characters = sum(len(text) for text in output_texts)
        total_output_words = sum(count_words(text) for text in output_texts)
        
        # Store output details in request.state for middleware to access
        http_request.state.output_details = {
            "character_length": total_output_characters,
            "word_count": total_output_words,
            "output_count": len(response.output)
        }
        
        # Add output metrics to trace span
        if TRACING_AVAILABLE and trace:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    current_span.set_attribute("asr.output_count", len(response.output))
                    current_span.set_attribute("asr.output.character_length", total_output_characters)
                    current_span.set_attribute("asr.output.word_count", total_output_words)
                    current_span.set_attribute("http.status_code", 200)
                    # Track response size (approximate)
                    try:
                        import json
                        response_size = len(json.dumps(response.dict()).encode('utf-8'))
                        current_span.set_attribute("http.response.size_bytes", response_size)
                    except Exception:
                        pass
                    # Add span event for successful completion
                    current_span.add_event("asr.inference.completed", {
                        "output_count": len(response.output),
                        "output_character_length": total_output_characters,
                        "output_word_count": total_output_words,
                        "status": "success"
                    })
            except Exception:
                pass  # Don't fail if tracing fails
        
        # Log completion
        processing_time = time.time() - start_time
        logger.info(
            "ASR inference completed in %.2fs, output_characters=%d, output_words=%d",
            processing_time,
            total_output_characters,
            total_output_words,
            extra={
                # Common input/output details structure (general fields for all services)
                "input_details": {
                    "audio_length_seconds": total_input_audio_duration,
                    "audio_length_ms": total_input_audio_duration * 1000.0,
                    "input_count": len(request.audio)
                },
                "output_details": {
                    "character_length": total_output_characters,
                    "word_count": total_output_words,
                    "output_count": len(response.output)
                },
                # Service metadata (for filtering)
                "service_id": request.config.serviceId if request.config else None,
                "source_language": request.config.language.sourceLanguage if request.config and request.config.language else None,
                "http_status_code": 200,
            }
        )
        
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
        # Extract context from request state for better error messages
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        model_name = getattr(http_request.state, "triton_model_name", None)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        
        # Get correlation ID for logging
        from ai4icore_logging import get_correlation_id
        correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
        
        # Trace the error if we're in a span context
        if TRACING_AVAILABLE and trace:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", type(e).__name__)
                    current_span.set_attribute("error.message", str(e))
                    current_span.set_attribute("http.status_code", 500)
                    current_span.set_status(Status(StatusCode.ERROR, str(e)))
                    current_span.record_exception(e)
                    if service_id:
                        current_span.set_attribute("asr.service_id", service_id)
                    if triton_endpoint:
                        current_span.set_attribute("triton.endpoint", triton_endpoint)
                    if model_name:
                        current_span.set_attribute("triton.model_name", model_name)
            except Exception:
                pass  # Don't fail if tracing fails
        
        # Log error with full context
        logger.error(
            f"ASR inference failed: {e}",
            extra={
                "context": {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "service_id": service_id,
                    "triton_endpoint": triton_endpoint,
                    "model_name": model_name,
                    "user_id": user_id,
                    "api_key_id": api_key_id,
                    "correlation_id": correlation_id,
                    "audio_count": len(request.audio) if hasattr(request, 'audio') else None,
                }
            },
            exc_info=True
        )
        
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


def calculate_audio_duration(audio_input) -> float:
    """Calculate audio duration in seconds from AudioInput"""
    try:
        if audio_input.audioContent:
            audio_bytes = base64.b64decode(audio_input.audioContent)
            return get_audio_duration(audio_bytes)
        elif audio_input.audioUri:
            # For URI, we can't calculate duration here without downloading
            # Return 0 and let service calculate it
            return 0.0
        return 0.0
    except Exception:
        return 0.0


def count_words(text: str) -> int:
    """Count words in text"""
    try:
        words = [word for word in text.split() if word.strip()]
        return len(words)
    except Exception:
        return 0


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
