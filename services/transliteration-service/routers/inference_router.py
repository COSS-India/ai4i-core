"""
Inference Router
FastAPI router for transliteration inference endpoints
"""

import logging
import time
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id

from models.transliteration_request import TransliterationInferenceRequest
from models.transliteration_response import TransliterationInferenceResponse
from repositories.transliteration_repository import TransliterationRepository
from services.transliteration_service import TransliterationService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.auth_utils import extract_auth_headers
from utils.validation_utils import (
    validate_language_pair, validate_service_id, validate_batch_size,
    InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError
)
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session
from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError,
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    TextProcessingError,
    ErrorDetail
)
import os
import httpx

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
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_MESSAGE,
    PROCESSING_FAILED,
    PROCESSING_FAILED_MESSAGE,
    MODEL_UNAVAILABLE,
    MODEL_UNAVAILABLE_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_MESSAGE,
    INTERNAL_SERVER_ERROR,
    INTERNAL_SERVER_ERROR_MESSAGE
)


API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")


logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("transliteration-service")

# Create router
inference_router = APIRouter(
    prefix="/api/v1/transliteration",
    tags=["Transliteration Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session (legacy - use get_tenant_db_session for tenant routing)"""
    return request.app.state.db_session_factory()


def create_triton_client(triton_url: str, api_key: str) -> TritonClient:
    """Factory function to create Triton client"""
    return TritonClient(triton_url=triton_url, api_key=api_key)


async def get_transliteration_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> TransliterationService:
    """
    Dependency to get configured transliteration service.
    
    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    repository = TransliterationRepository(db)
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
                "Transliteration service requires Model Management database resolution."
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
    
    # Create default Triton client with the resolved endpoint
    default_triton_client = get_triton_client_for_endpoint(triton_endpoint)
    
    return TransliterationService(
        repository=repository, 
        text_service=text_service,
        get_triton_client_func=get_triton_client_for_endpoint,
        model_management_client=model_management_client,
        redis_client=redis_client,
        cache_ttl_seconds=cache_ttl_seconds,
        default_triton_client=default_triton_client
    )


async def _enforce_tenant_and_service_checks(http_request: Request, service_name: str = "transliteration"):
    """
    Enforce tenant subscription, tenant status (ACTIVE) and global service active flag.
    Execution order:
      1) If tenant context exists, ensure tenant subscribes to this service
      2) Ensure the service is globally active via /list/services
      3) If tenant context exists, ensure tenant.status == ACTIVE
    """
    auth_header = http_request.headers.get("Authorization") or http_request.headers.get("authorization")

    # Build headers to forward
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header
    x_api_key = http_request.headers.get("X-API-Key") or http_request.headers.get("x-api-key")
    if x_api_key:
        headers["X-API-Key"] = x_api_key
    x_auth_source = http_request.headers.get("X-Auth-Source") or http_request.headers.get("x-auth-source")
    if x_auth_source:
        headers["X-Auth-Source"] = x_auth_source

    # If tenant context exists, ensure tenant is subscribed to the service FIRST
    tenant_id = getattr(http_request.state, "tenant_id", None)
    tenant_data = None
    if tenant_id:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/view/tenant", params={"tenant_id": tenant_id}, headers=headers)
                if resp.status_code == 200:
                    tenant_data = resp.json()
                    subscriptions = [str(s).lower() for s in (tenant_data.get("subscriptions") or [])]
                    if service_name.lower() not in subscriptions:
                        raise HTTPException(status_code=403, detail={"code": "SERVICE_NOT_SUBSCRIBED", "message": f"Tenant '{tenant_id}' is not subscribed to '{service_name}'"})
                elif resp.status_code == 404:
                    raise HTTPException(status_code=403, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant not found"})
                else:
                    raise HTTPException(status_code=503, detail={"code": "TENANT_CHECK_FAILED", "message": "Failed to verify tenant information"})
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to retrieve tenant info for tenant_id={tenant_id}: {e}")
            raise HTTPException(status_code=503, detail={"code": "TENANT_CHECK_FAILED", "message": "Failed to verify tenant information"})

    # Next, ensure the service is globally active
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            svc_resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/list/services", headers=headers if headers else None)
            if svc_resp.status_code == 200:
                services = svc_resp.json().get("services", [])
                svc_entry = next((s for s in services if str(s.get("service_name")).lower() == service_name.lower()), None)
                if not svc_entry or not svc_entry.get("is_active", False):
                    raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Transliteration service is not active at the moment. Please contact your administrator").dict())
            else:
                raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Cannot detect service availability. Please contact your administrator").dict())
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Transliteration service is temporarily unavailable. Please try again in a few minutes.").dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to verify service active state for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Transliteration service is temporarily unavailable. Please try again in a few minutes.").dict())

    # Finally, if tenant context present, enforce tenant status (must be ACTIVE)
    if tenant_id:
        try:
            if not tenant_data:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/view/tenant", params={"tenant_id": tenant_id}, headers=headers)
                    if resp.status_code == 200:
                        tenant_data = resp.json()
                    elif resp.status_code == 404:
                        raise HTTPException(status_code=403, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant not found"})
                    else:
                        raise HTTPException(status_code=503, detail={"code": "TENANT_CHECK_FAILED", "message": "Failed to verify tenant status"})

            status_val = (tenant_data.get("status") or "").upper()
            if status_val != "ACTIVE":
                raise HTTPException(status_code=403, detail={"code": "TENANT_INACTIVE", "message": f"Tenant status is {status_val}. Access denied."})
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to verify tenant status for tenant_id={tenant_id}: {e}")
            raise HTTPException(status_code=503, detail={"code": "TENANT_CHECK_FAILED", "message": "Failed to verify tenant status"})


async def enforce_transliteration_checks(request: Request):
    """FastAPI dependency that enforces tenant and service checks for Transliteration before other dependencies run."""
    # the service name is coming from multitenant SubscriptionType enum
    await _enforce_tenant_and_service_checks(request, service_name="transliteration")

# Add as a router-level dependency so it runs before path-operation dependencies like get_transliteration_service
inference_router.dependencies.insert(0, Depends(enforce_transliteration_checks))

@inference_router.post(
    "/inference",
    response_model=TransliterationInferenceResponse,
    summary="Perform batch transliteration inference",
    description="Transliterate text from source language to target language for one or more text inputs (max 100)"
)
async def run_inference(
    request: TransliterationInferenceRequest,
    http_request: Request,
    transliteration_service: TransliterationService = Depends(get_transliteration_service)
) -> TransliterationInferenceResponse:
    """
    Run transliteration inference on the given request.
    
    Creates detailed trace spans for the entire inference operation.
    """
    # Create a span for the entire inference operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _run_transliteration_inference_impl(request, http_request, transliteration_service)
    
    with tracer.start_as_current_span("transliteration.inference") as span:
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
            span.set_attribute("transliteration.input_count", len(request.input))
            span.set_attribute("transliteration.service_id", request.config.serviceId)
            span.set_attribute("transliteration.source_language", request.config.language.sourceLanguage)
            span.set_attribute("transliteration.target_language", request.config.language.targetLanguage)
            span.set_attribute("transliteration.is_sentence", request.config.isSentence)
            span.set_attribute("transliteration.num_suggestions", request.config.numSuggestions)
            
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
            span.add_event("transliteration.inference.started", {
                "input_count": len(request.input),
                "service_id": request.config.serviceId,
                "source_language": request.config.language.sourceLanguage,
                "target_language": request.config.language.targetLanguage,
                "is_sentence": request.config.isSentence
            })

            logger.info(
                "Processing Transliteration inference request with %d text input(s), user_id=%s api_key_id=%s session_id=%s",
                len(request.input),
                user_id,
                api_key_id,
                session_id,
            )

            # Run inference
            response = await transliteration_service.run_inference(
                request=request,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                auth_headers=extract_auth_headers(http_request)
            )
            
            # Add response metadata
            span.set_attribute("transliteration.output_count", len(response.output))
            span.set_attribute("http.status_code", 200)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("transliteration.inference.completed", {
                "output_count": len(response.output),
                "status": "success"
            })
            span.set_status(Status(StatusCode.OK))
            logger.info("Transliteration inference completed successfully")
            return response

        except (InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError) as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("transliteration.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Validation error in Transliteration inference: %s", exc)
            raise HTTPException(
                status_code=400,
                detail=ErrorDetail(code=INVALID_REQUEST, message=INVALID_REQUEST_MESSAGE).dict()
            ) from exc

        except (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError, TextProcessingError) as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", getattr(exc, 'status_code', 503))
            span.add_event("transliteration.inference.failed", {
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
            span.add_event("transliteration.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.error("Transliteration inference failed: %s", exc, exc_info=True)
            
            # Extract context from request state for better error messages
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            # Return appropriate error based on exception type
            if "Triton" in str(exc) or "triton" in str(exc).lower():
                error_code = MODEL_UNAVAILABLE if model_name else SERVICE_UNAVAILABLE
                error_message = MODEL_UNAVAILABLE_MESSAGE if model_name else SERVICE_UNAVAILABLE_MESSAGE
                raise HTTPException(
                    status_code=503,
                    detail=ErrorDetail(code=error_code, message=error_message).dict()
                ) from exc
            elif "transliteration" in str(exc).lower() or "failed" in str(exc).lower():
                raise HTTPException(
                    status_code=500,
                    detail=ErrorDetail(code=PROCESSING_FAILED, message=PROCESSING_FAILED_MESSAGE).dict()
                ) from exc
            else:
                raise HTTPException(
                    status_code=500,
                    detail=ErrorDetail(code=INTERNAL_SERVER_ERROR, message=INTERNAL_SERVER_ERROR_MESSAGE).dict()
                ) from exc


async def _run_transliteration_inference_impl(
    request: TransliterationInferenceRequest,
    http_request: Request,
    transliteration_service: TransliterationService,
) -> TransliterationInferenceResponse:
    """Fallback implementation when tracing is not available."""
    # Validate request
    validate_service_id(request.config.serviceId)
    validate_language_pair(
        request.config.language.sourceLanguage,
        request.config.language.targetLanguage
    )
    validate_batch_size(len(request.input), max_size=100)
    
    # Validate top_k for sentence level
    if request.config.numSuggestions > 0 and request.config.isSentence:
        raise HTTPException(
            status_code=400, 
            detail="numSuggestions (top_k) is not valid for sentence level transliteration"
        )
    
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    logger.info(
        "Processing Transliteration inference request with %d text input(s), user_id=%s api_key_id=%s session_id=%s",
        len(request.input),
        user_id,
        api_key_id,
        session_id,
    )

    response = await transliteration_service.run_inference(
        request=request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
        auth_headers=extract_auth_headers(http_request)
    )
    logger.info("Transliteration inference completed successfully")
    return response


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available transliteration models",
    description="Get list of supported transliteration models and language pairs"
)
async def list_models() -> Dict[str, Any]:
    """List available transliteration models and language pairs"""
    return {
        "models": [
            {
                "model_id": "ai4bharat/indicxlit",
                "provider": "AI4Bharat",
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                    "mai", "brx", "mni", "sat", "gom"
                ],
                "description": "IndicXlit model supporting transliteration for 20+ Indic languages",
                "max_batch_size": 100,
                "supports_sentence_level": True,
                "supports_word_level": True,
                "supports_top_k": True
            }
        ],
        "total_models": 1
    }


@inference_router.get(
    "/services",
    response_model=Dict[str, Any],
    summary="List available transliteration services",
    description="Get list of supported transliteration services with their Triton endpoints"
)
async def list_services() -> Dict[str, Any]:
    """List available transliteration services and their endpoints"""
    return {
        "services": [
            {
                "service_id": "ai4bharat/indicxlit",
                "model_id": "ai4bharat/indicxlit",
                "triton_endpoint": "13.200.133.97:8000",
                "triton_model": "transliteration",
                "provider": "AI4Bharat",
                "description": "IndicXlit model supporting transliteration for 20+ Indic languages",
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                    "mai", "brx", "mni", "sat", "gom"
                ]
            },
            {
                "service_id": "indicxlit",
                "model_id": "ai4bharat/indicxlit",
                "triton_endpoint": "13.200.133.97:8000",
                "triton_model": "transliteration",
                "provider": "AI4Bharat",
                "description": "IndicXlit model supporting transliteration for 20+ Indic languages (alias)",
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                    "mai", "brx", "mni", "sat", "gom"
                ]
            }
        ],
        "total_services": 2
    }


@inference_router.get(
    "/languages",
    response_model=Dict[str, Any],
    summary="Get supported languages",
    description="Get list of supported languages for a specific transliteration model or service"
)
async def list_languages(
    model_id: Optional[str] = Query(None, description="Model ID to get languages for"),
    service_id: Optional[str] = Query(None, description="Service ID to get languages for")
) -> Dict[str, Any]:
    """List supported languages for a specific transliteration model or service"""
    
    # Service ID to Model ID mapping
    SERVICE_TO_MODEL_MAP = {
        "ai4bharat/indicxlit": "ai4bharat/indicxlit",
        "indicxlit": "ai4bharat/indicxlit"
    }
    
    # Log received parameters for debugging
    logger.info(f"list_languages called with service_id={service_id}, model_id={model_id}")
    
    # Determine model_id from service_id if provided
    if service_id:
        if service_id in SERVICE_TO_MODEL_MAP:
            model_id = SERVICE_TO_MODEL_MAP[service_id]
            logger.info(f"Mapped service_id '{service_id}' to model_id '{model_id}'")
        else:
            logger.warning(f"Service '{service_id}' not found in mapping")
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_id}' not found. Available services: {', '.join(SERVICE_TO_MODEL_MAP.keys())}"
            )
    
    # Default to IndicXlit model if neither provided
    if not model_id:
        model_id = "ai4bharat/indicxlit"
        logger.info(f"No model_id provided, defaulting to '{model_id}'")
    
    # Hardcoded language data by model_id
    if model_id == "ai4bharat/indicxlit":
        return {
            "model_id": "ai4bharat/indicxlit",
            "provider": "AI4Bharat",
            "supported_languages": [
                "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                "mai", "brx", "mni", "sat", "gom"
            ],
            "language_details": [
                {"code": "en", "name": "English"},
                {"code": "hi", "name": "Hindi"},
                {"code": "ta", "name": "Tamil"},
                {"code": "te", "name": "Telugu"},
                {"code": "kn", "name": "Kannada"},
                {"code": "ml", "name": "Malayalam"},
                {"code": "bn", "name": "Bengali"},
                {"code": "gu", "name": "Gujarati"},
                {"code": "mr", "name": "Marathi"},
                {"code": "pa", "name": "Punjabi"},
                {"code": "or", "name": "Odia"},
                {"code": "as", "name": "Assamese"},
                {"code": "ur", "name": "Urdu"},
                {"code": "sa", "name": "Sanskrit"},
                {"code": "ks", "name": "Kashmiri"},
                {"code": "ne", "name": "Nepali"},
                {"code": "sd", "name": "Sindhi"},
                {"code": "kok", "name": "Konkani"},
                {"code": "doi", "name": "Dogri"},
                {"code": "mai", "name": "Maithili"},
                {"code": "brx", "name": "Bodo"},
                {"code": "mni", "name": "Manipuri"},
                {"code": "sat", "name": "Santali"},
                {"code": "gom", "name": "Goan Konkani"}
            ],
            "total_languages": 24
        }
    else:
        raise HTTPException(
            status_code=404, 
            detail=f"Model '{model_id}' not found. Available models: ai4bharat/indicxlit"
        )

