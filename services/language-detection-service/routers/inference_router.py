import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request

from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_logger, get_correlation_id

from models.language_detection_request import LanguageDetectionInferenceRequest
from models.language_detection_response import LanguageDetectionInferenceResponse
from repositories.language_detection_repository import LanguageDetectionRepository
from services.language_detection_service import LanguageDetectionService
from services.text_service import TextService
from utils.triton_client import TritonClient
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session
import os
import httpx
from middleware.exceptions import ErrorDetail
from fastapi import Depends

logger = get_logger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("language-detection-service")

inference_router = APIRouter(
    prefix="/api/v1/language-detection",
    tags=["Language Detection"],
    dependencies=[Depends(AuthProvider)]
)


API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")


async def get_language_detection_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session)
) -> LanguageDetectionService:
    """
    Dependency to construct LanguageDetectionService with Triton client resolved
    exclusively via Model Management (no environment variable fallback).

    ModelResolutionMiddleware (from ai4icore_model_management) must:
    - Extract config.serviceId from the request body
    - Resolve serviceId → triton_endpoint + model_name
    - Attach to request.state:
        - request.state.triton_endpoint
        - request.state.triton_model_name
        - request.state.service_id
    """
    repository = LanguageDetectionRepository(db)
    text_service = TextService()

    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.app.state, "triton_api_key", "")

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
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Request must include config.serviceId. "
                "Language Detection service requires Model Management database resolution."
            ),
        )

    # Get resolved model name from middleware (MUST be resolved by Model Management)
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Model Management failed to resolve Triton model name for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            ),
        )
    
    # Log removed - middleware handles request/response logging

    triton_client = TritonClient(triton_endpoint, triton_api_key or None)

    # LanguageDetectionService already supports dynamic endpoints internally if needed;
    # we pass the resolved client as the primary path.
    def get_triton_client_for_endpoint(endpoint: str) -> TritonClient:
        return TritonClient(triton_url=endpoint, api_key=triton_api_key or None)

    return LanguageDetectionService(
        repository,
        text_service,
        triton_client,
        get_triton_client_for_endpoint,
        resolved_model_name=model_name,
    )

async def _enforce_tenant_and_service_checks(http_request: Request, service_name: str = "language-detection"):
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
                    raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Language Detection service is not active at the moment. Please contact your administrator").dict())
            else:
                raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Cannot detect service availability. Please contact your administrator").dict())
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Language Detection service is temporarily unavailable. Please try again in a few minutes.").dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to verify service active state for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Language Detection service is temporarily unavailable. Please try again in a few minutes.").dict())

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


async def enforce_language_detection_checks(request: Request):
    """FastAPI dependency that enforces tenant and service checks for Language Detection before other dependencies run."""
    # the service name is coming from multitenant SubscriptionType enum
    await _enforce_tenant_and_service_checks(request, service_name="language_detection")

# Add as a router-level dependency so it runs before path-operation dependencies like get_language_detection_service
inference_router.dependencies.insert(0, Depends(enforce_language_detection_checks))

@inference_router.post(
    "/inference",
    response_model=LanguageDetectionInferenceResponse,
    summary="Detect language of text",
    description="Detect the language and script of input text using IndicLID model"
)
async def run_inference(
    request_body: LanguageDetectionInferenceRequest,
    http_request: Request,
    language_detection_service: LanguageDetectionService = Depends(get_language_detection_service)
) -> LanguageDetectionInferenceResponse:
    """
    Run language detection inference on the given request.
    
    Creates detailed trace spans for the entire inference operation.
    """
    # Create a span for the entire inference operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _run_inference_impl(request_body, http_request, language_detection_service)
    
    with tracer.start_as_current_span("language-detection.inference") as span:
        try:
            # Extract auth context from request.state (if middleware is configured)
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            session_id = getattr(http_request.state, "session_id", None)
            api_key_name = getattr(http_request.state, "api_key_name", None)
            
            # Get correlation ID for log/trace correlation
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)

            # Add request metadata to span
            span.set_attribute("language-detection.input_count", len(request_body.input))
            span.set_attribute("language-detection.service_id", request_body.config.serviceId if request_body.config else "unknown")
            
            # Track request size (approximate)
            try:
                import json
                request_size = len(json.dumps(request_body.dict()).encode('utf-8'))
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
            span.add_event("language-detection.inference.started", {
                "input_count": len(request_body.input),
                "service_id": request_body.config.serviceId if request_body.config else "unknown"
            })

            # Log removed - middleware handles request/response logging

            # Run inference
            response = await language_detection_service.run_inference(
                request=request_body,
                api_key_name=api_key_name,
                user_id=user_id
            )
            
            # Add response metadata
            span.set_attribute("language-detection.output_count", len(response.output))
            span.set_attribute("http.status_code", 200)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("language-detection.inference.completed", {
                "output_count": len(response.output)
            })
            
            # Log removed - middleware handles request/response logging
            return response
            
        except ValueError as exc:
            logger.warning("Validation error in Language Detection inference: %s", exc)
            if tracer:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", type(exc).__name__)
                    current_span.set_attribute("error.message", str(exc))
                    current_span.set_status(Status(StatusCode.ERROR, str(exc)))
                    current_span.record_exception(exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            error_detail = str(exc)
            
            # Record error in Jaeger span
            if tracer:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", type(exc).__name__)
                    current_span.set_attribute("error.message", error_detail)
                    current_span.set_status(Status(StatusCode.ERROR, error_detail))
                    current_span.record_exception(exc)
            
            # Include model management context in error message
            if service_id and triton_endpoint:
                error_detail = (
                    f"Language Detection inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                    "Please verify the model is registered in Model Management and the Triton server is accessible."
                )
            elif service_id:
                error_detail = (
                    f"Language Detection inference failed for serviceId '{service_id}': {error_detail}. "
                    "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
                )
            else:
                error_detail = (
                    f"Language Detection inference failed: {error_detail}. "
                    "Please ensure config.serviceId is provided and the service is registered in Model Management."
                )
            
            logger.error("Language Detection inference failed: %s (serviceId=%s, endpoint=%s)", 
                        exc, service_id, triton_endpoint)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            ) from exc


async def _run_inference_impl(
    request_body: LanguageDetectionInferenceRequest,
    http_request: Request,
    language_detection_service: LanguageDetectionService
) -> LanguageDetectionInferenceResponse:
    """Fallback implementation when tracing is not available."""
    try:
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_name = getattr(http_request.state, 'api_key_name', None)
        
        # Log removed - middleware handles request/response logging
        
        response = await language_detection_service.run_inference(
            request=request_body,
            api_key_name=api_key_name,
            user_id=user_id
        )
        
        # Log removed - middleware handles request/response logging
        return response
        
    except ValueError as exc:
        logger.warning("Validation error in Language Detection inference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        error_detail = str(exc)
        
        # Include model management context in error message
        if service_id and triton_endpoint:
            error_detail = (
                f"Language Detection inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                "Please verify the model is registered in Model Management and the Triton server is accessible."
            )
        elif service_id:
            error_detail = (
                f"Language Detection inference failed for serviceId '{service_id}': {error_detail}. "
                "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
            )
        else:
            error_detail = (
                f"Language Detection inference failed: {error_detail}. "
                "Please ensure config.serviceId is provided and the service is registered in Model Management."
            )
        
        logger.error("Language Detection inference failed: %s (serviceId=%s, endpoint=%s)", 
                    exc, service_id, triton_endpoint)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        ) from exc


@inference_router.get(
    "/languages",
    response_model=Dict[str, Any],
    summary="Get supported languages",
    description="Get list of supported languages and scripts for language detection"
)
async def list_languages() -> Dict[str, Any]:
    return {
        "languages": [
            {"code": "as", "name": "Assamese", "scripts": ["Beng", "Latn"]},
            {"code": "bn", "name": "Bengali", "scripts": ["Beng", "Latn"]},
            {"code": "brx", "name": "Bodo", "scripts": ["Deva", "Latn"]},
            {"code": "doi", "name": "Dogri", "scripts": ["Deva", "Latn"]},
            {"code": "en", "name": "English", "scripts": ["Latn"]},
            {"code": "gu", "name": "Gujarati", "scripts": ["Gujr", "Latn"]},
            {"code": "hi", "name": "Hindi", "scripts": ["Deva", "Latn"]},
            {"code": "kn", "name": "Kannada", "scripts": ["Knda", "Latn"]},
            {"code": "ks", "name": "Kashmiri", "scripts": ["Arab", "Deva", "Latn"]},
            {"code": "kok", "name": "Konkani", "scripts": ["Deva", "Latn"]},
            {"code": "mai", "name": "Maithili", "scripts": ["Deva", "Latn"]},
            {"code": "ml", "name": "Malayalam", "scripts": ["Mlym", "Latn"]},
            {"code": "mni", "name": "Manipuri", "scripts": ["Beng", "Mtei", "Latn"]},
            {"code": "mr", "name": "Marathi", "scripts": ["Deva", "Latn"]},
            {"code": "ne", "name": "Nepali", "scripts": ["Deva", "Latn"]},
            {"code": "or", "name": "Odia", "scripts": ["Orya", "Latn"]},
            {"code": "pa", "name": "Punjabi", "scripts": ["Guru", "Latn"]},
            {"code": "sa", "name": "Sanskrit", "scripts": ["Deva", "Latn"]},
            {"code": "sat", "name": "Santali", "scripts": ["Olck"]},
            {"code": "sd", "name": "Sindhi", "scripts": ["Arab", "Latn"]},
            {"code": "ta", "name": "Tamil", "scripts": ["Taml", "Latn"]},
            {"code": "te", "name": "Telugu", "scripts": ["Telu", "Latn"]},
            {"code": "ur", "name": "Urdu", "scripts": ["Arab", "Latn"]},
            {"code": "other", "name": "Other", "scripts": ["Latn"]}
        ],
        "total_languages": 23,
        "model": "ai4bharat/indiclid"
    }


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available language detection models",
    description="Get list of supported language detection models"
)
async def list_models() -> Dict[str, Any]:
    return {
        "models": [
            {
                "model_id": "ai4bharat/indiclid",
                "provider": "AI4Bharat",
                "supported_languages": 23,
                "description": "IndicLID model for identifying Indian language text and scripts",
                "max_batch_size": 100
            }
        ],
        "total_models": 1
    }

