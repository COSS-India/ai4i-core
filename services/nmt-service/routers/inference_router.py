"""
Inference Router
FastAPI router for NMT inference endpoints
"""

import logging
import time
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id, get_logger

from models.nmt_request import NMTInferenceRequest
from models.nmt_response import NMTInferenceResponse
from repositories.nmt_repository import NMTRepository
from services.nmt_service import NMTService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.auth_utils import extract_auth_headers
from utils.text_utils import count_words
from utils.validation_utils import (
    validate_language_pair, validate_service_id, validate_batch_size,
    InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError
)
from middleware.auth_provider import AuthProvider
from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError,
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    TextProcessingError,
    ErrorDetail
)
from middleware.exceptions import AuthenticationError, AuthorizationError
from middleware.tenant_db_dependency import get_tenant_db_session

from services.constants.error_messages import (
    NO_TEXT_INPUT,
    NO_TEXT_INPUT_NMT_MESSAGE,
    TEXT_TOO_SHORT,
    TEXT_TOO_SHORT_NMT_MESSAGE,
    TEXT_TOO_LONG,
    TEXT_TOO_LONG_NMT_MESSAGE,
    INVALID_CHARACTERS,
    INVALID_CHARACTERS_NMT_MESSAGE,
    EMPTY_INPUT,
    EMPTY_INPUT_NMT_MESSAGE,
    SAME_LANGUAGE_ERROR,
    SAME_LANGUAGE_ERROR_MESSAGE,
    LANGUAGE_PAIR_NOT_SUPPORTED,
    LANGUAGE_PAIR_NOT_SUPPORTED_MESSAGE,
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_NMT_MESSAGE,
    TRANSLATION_FAILED,
    TRANSLATION_FAILED_MESSAGE,
    MODEL_UNAVAILABLE,
    MODEL_UNAVAILABLE_NMT_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_NMT_MESSAGE,
    INTERNAL_SERVER_ERROR,
    INTERNAL_SERVER_ERROR_MESSAGE
)

# Use get_logger from ai4icore_logging to ensure JSON formatting and proper handlers
logger = get_logger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("nmt-service")

# Create router
inference_router = APIRouter(
    prefix="/api/v1/nmt",
    tags=["NMT Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session (legacy - use get_tenant_db_session for tenant routing)"""
    return request.app.state.db_session_factory()


async def get_nmt_service(request: Request, db: AsyncSession = Depends(get_tenant_db_session)) -> NMTService:
    """
    Dependency to get configured NMT service.
    
    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    repository = NMTRepository(db)
    text_service = TextService()
    
    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.state, "triton_api_key", None)
    
    if not triton_endpoint:
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        
        if service_id:
            error_detail = (
                f"Model Management did not resolve serviceId: {service_id} and no default endpoint is allowed. "
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
                "NMT service requires Model Management database resolution."
            ),
        )
    
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
        raise HTTPException(
            status_code=500,
            detail=(
                f"Model Management did not resolve model name for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            ),
        )
    
    logger.info(
        "Using Triton endpoint=%s model_name=%s for serviceId=%s from Model Management",
        triton_endpoint,
        model_name,
        getattr(request.state, "service_id", "unknown"),
    )
    
    # Factory function to create Triton clients for different endpoints
    def get_triton_client_for_endpoint(endpoint: str) -> TritonClient:
        """Create Triton client for specific endpoint"""
        # Strip http:// or https:// scheme from URL if present
        triton_url = endpoint
        if triton_url.startswith(('http://', 'https://')):
            triton_url = triton_url.split('://', 1)[1]
        return TritonClient(
            triton_url=triton_url,
            api_key=triton_api_key
        )
    
    # Get Redis client and Model Management client from app state
    redis_client = getattr(request.app.state, "redis_client", None)
    model_management_client = getattr(request.app.state, "model_management_client", None)
    
    if not model_management_client:
        raise HTTPException(
            status_code=500,
            detail="Model Management client not available. Service configuration error."
        )
    
    # Get cache TTL from Model Management client config
    cache_ttl_seconds = getattr(model_management_client, "cache_ttl_seconds", 300)
    
    return NMTService(
        repository=repository, 
        text_service=text_service,
        get_triton_client_func=get_triton_client_for_endpoint,
        model_management_client=model_management_client,
        redis_client=redis_client,
        cache_ttl_seconds=cache_ttl_seconds
    )


@inference_router.post(
    "/inference",
    response_model=NMTInferenceResponse,
    summary="Perform batch NMT inference",
    description="Translate text from source language to target language for one or more text inputs (max 90)"
)
async def run_inference(
    request: NMTInferenceRequest,
    http_request: Request,
    nmt_service: NMTService = Depends(get_nmt_service)
) -> NMTInferenceResponse:
    """
    Run NMT inference on the given request.
    
    Creates detailed trace spans for the entire inference operation.
    """
    # Create a span for the entire inference operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _run_nmt_inference_impl(request, http_request, nmt_service)
    
    with tracer.start_as_current_span("nmt.inference") as span:
        try:
            # Extract auth context from request.state (if middleware is configured)
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            session_id = getattr(http_request.state, "session_id", None)
            
            # Get correlation ID for log/trace correlation
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)

            # Calculate input metrics (character length and word count)
            input_texts = [text_input.source for text_input in request.input]
            total_input_characters = sum(len(text) for text in input_texts)
            total_input_words = sum(count_words(text) for text in input_texts)
            
            # Add request metadata to span
            span.set_attribute("nmt.input_count", len(request.input))
            span.set_attribute("nmt.service_id", request.config.serviceId)
            span.set_attribute("nmt.source_language", request.config.language.sourceLanguage)
            span.set_attribute("nmt.target_language", request.config.language.targetLanguage)
            if request.config.language.sourceScriptCode:
                span.set_attribute("nmt.source_script_code", request.config.language.sourceScriptCode)
            if request.config.language.targetScriptCode:
                span.set_attribute("nmt.target_script_code", request.config.language.targetScriptCode)
            
            # Add input metrics to span
            span.set_attribute("nmt.input.character_length", total_input_characters)
            span.set_attribute("nmt.input.word_count", total_input_words)
            
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
            span.add_event("nmt.inference.started", {
                "input_count": len(request.input),
                "service_id": request.config.serviceId,
                "source_language": request.config.language.sourceLanguage,
                "target_language": request.config.language.targetLanguage
            })

            logger.info(
                "Processing NMT inference request with %d text input(s), input_characters=%d, input_words=%d, user_id=%s api_key_id=%s session_id=%s",
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
                    "target_language": request.config.language.targetLanguage,
                }
            )

            # Run inference
            response = await nmt_service.run_inference(
                request=request,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                auth_headers=extract_auth_headers(http_request)
            )
            
            # Calculate output metrics (character length and word count) for successful responses
            output_texts = [output.target for output in response.output]
            total_output_characters = sum(len(text) for text in output_texts)
            total_output_words = sum(count_words(text) for text in output_texts)
            
            # Add response metadata
            span.set_attribute("nmt.output_count", len(response.output))
            span.set_attribute("http.status_code", 200)
            
            # Add output metrics to span (for 200 responses)
            span.set_attribute("nmt.output.character_length", total_output_characters)
            span.set_attribute("nmt.output.word_count", total_output_words)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("nmt.inference.completed", {
                "output_count": len(response.output),
                "output_character_length": total_output_characters,
                "output_word_count": total_output_words,
                "status": "success"
            })
            span.set_status(Status(StatusCode.OK))
            logger.info(
                "NMT inference completed successfully, output_characters=%d, output_words=%d",
                total_output_characters,
                total_output_words,
                extra={
                    # Common input/output details structure (general fields for all services)
                    "input_details": {
                        "character_length": total_input_characters,
                        "word_count": total_input_words,
                        "input_count": len(request.input)
                    },
                    "output_details": {
                        "character_length": total_output_characters,
                        "word_count": total_output_words,
                        "output_count": len(response.output)
                    },
                    # Service metadata (for filtering)
                    "service_id": request.config.serviceId,
                    "source_language": request.config.language.sourceLanguage,
                    "target_language": request.config.language.targetLanguage,
                    "http_status_code": 200,
                }
            )
            return response

        except (InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError) as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("nmt.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Validation error in NMT inference: %s", exc)
            raise HTTPException(
                status_code=400,
                detail=ErrorDetail(code=INVALID_REQUEST, message=INVALID_REQUEST_NMT_MESSAGE).dict()
            ) from exc

        except (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError, TextProcessingError) as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", getattr(exc, 'status_code', 503))
            span.add_event("nmt.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            # Re-raise service-specific errors (they will be handled by error handler middleware)
            raise

        except Exception as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 500)
            span.add_event("nmt.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.error("NMT inference failed: %s", exc, exc_info=True)
            
            # Extract context from request state for better error messages
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            # Return appropriate error based on exception type
            if "Triton" in str(exc) or "triton" in str(exc).lower():
                error_code = MODEL_UNAVAILABLE if model_name else SERVICE_UNAVAILABLE
                error_message = MODEL_UNAVAILABLE_NMT_MESSAGE if model_name else SERVICE_UNAVAILABLE_NMT_MESSAGE
                raise HTTPException(
                    status_code=503,
                    detail=ErrorDetail(code=error_code, message=error_message).dict()
                ) from exc
            elif "translation" in str(exc).lower() or "failed" in str(exc).lower():
                raise HTTPException(
                    status_code=500,
                    detail=ErrorDetail(code=TRANSLATION_FAILED, message=TRANSLATION_FAILED_MESSAGE).dict()
                ) from exc
            else:
                raise HTTPException(
                    status_code=500,
                    detail=ErrorDetail(code=INTERNAL_SERVER_ERROR, message=INTERNAL_SERVER_ERROR_MESSAGE).dict()
                ) from exc


async def _run_nmt_inference_impl(
    request: NMTInferenceRequest,
    http_request: Request,
    nmt_service: NMTService,
) -> NMTInferenceResponse:
    """Fallback implementation when tracing is not available."""
    # Validate request
    validate_service_id(request.config.serviceId)
    validate_language_pair(
        request.config.language.sourceLanguage,
        request.config.language.targetLanguage
    )
    validate_batch_size(len(request.input))
    
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    logger.info(
        "Processing NMT inference request with %d text input(s), user_id=%s api_key_id=%s session_id=%s",
        len(request.input),
        user_id,
        api_key_id,
        session_id,
    )

    response = await nmt_service.run_inference(
        request=request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
        auth_headers=extract_auth_headers(http_request)
    )
    logger.info("NMT inference completed successfully")
    return response
 
