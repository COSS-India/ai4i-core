"""
Inference router for Speaker Diarization service.

Exposes a ULCA-style speaker diarization inference endpoint:
- POST /api/v1/speaker-diarization/inference
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_logger, get_correlation_id

from models.speaker_diarization_request import SpeakerDiarizationInferenceRequest
from models.speaker_diarization_response import SpeakerDiarizationInferenceResponse
from repositories.speaker_diarization_repository import SpeakerDiarizationRepository
from services.speaker_diarization_service import SpeakerDiarizationService
from utils.triton_client import TritonClient, TritonInferenceError
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session
from middleware.tenant_context import try_get_tenant_context
import os
import httpx
from middleware.exceptions import ErrorDetail
from fastapi import Depends

logger = get_logger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("speaker-diarization-service")

inference_router = APIRouter(
    prefix="/api/v1/speaker-diarization",
    tags=["Speaker Diarization Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session (legacy - use get_tenant_db_session for tenant routing)"""
    return request.app.state.db_session_factory()


async def get_speaker_diarization_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session)
) -> SpeakerDiarizationService:
    """
    Dependency to construct SpeakerDiarizationService with configured Triton client and repository.

    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    triton_endpoint: str = getattr(request.state, "triton_endpoint", None)
    triton_api_key: str = getattr(request.app.state, "triton_api_key", "")
    triton_timeout: float = getattr(request.app.state, "triton_timeout", 300.0)

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
                "Speaker Diarization service requires Model Management database resolution."
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
    
    logger.info(
        "Using Triton endpoint=%s model_name=%s for serviceId=%s from Model Management",
        triton_endpoint,
        model_name,
        getattr(request.state, "service_id", "unknown"),
    )

    triton_client = TritonClient(triton_endpoint, triton_api_key or None, triton_timeout, model_name=model_name)
    repository = SpeakerDiarizationRepository(db)
    return SpeakerDiarizationService(triton_client=triton_client, repository=repository)


async def _enforce_tenant_and_service_checks(http_request: Request, service_name: str):
    """
    Enforce tenant subscription, tenant status (ACTIVE) and global service active flag.
    Execution order:
      1) If tenant context exists, ensure tenant subscribes to this service
      2) Ensure the service is globally active via /list/services
      3) If tenant context exists, ensure tenant.status == ACTIVE.
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

    # Determine tenant context in a best-effort way.
    tenant_context = getattr(http_request.state, "tenant_context", None)
    jwt_payload = getattr(http_request.state, "jwt_payload", None)
    tenant_id_from_jwt = jwt_payload.get("tenant_id") if jwt_payload else None

    tenant_data = tenant_context if tenant_context else None
    tenant_id = tenant_context.get("tenant_id") if tenant_context else (tenant_id_from_jwt or None)

    # If still no tenant info, attempt best-effort resolution (returns None for normal users)
    if not tenant_id:
        try:
            resolved = await try_get_tenant_context(http_request)
            if resolved:
                tenant_context = resolved
                tenant_id = tenant_context.get("tenant_id")
                tenant_data = tenant_context
            else:
                tenant_id = None
        except Exception as e:
            logger.debug(f"try_get_tenant_context discovery failed: {e}")
    
    # tenant_data may already be populated from tenant_context; only call API gateway if we still need tenant info
    if tenant_id:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/admin/view/tenant", params={"tenant_id": tenant_id}, headers=headers)
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
                    raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Speaker Diarization service is not active at the moment. Please contact your administrator").dict())
            else:
                raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Cannot detect service availability. Please contact your administrator").dict())
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Speaker Diarization service is temporarily unavailable. Please try again in a few minutes.").dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to verify service active state for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Speaker Diarization service is temporarily unavailable. Please try again in a few minutes.").dict())

    # Finally, if tenant context present, enforce tenant status (must be ACTIVE)
    if tenant_id:
        try:
            if not tenant_data:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/admin/view/tenant", params={"tenant_id": tenant_id}, headers=headers)
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


async def enforce_speaker_diarization_checks(request: Request):
    """FastAPI dependency that enforces tenant and service checks for Speaker Diarization before other dependencies run."""
    # the service name is coming from multitenant SubscriptionType enum
    await _enforce_tenant_and_service_checks(request, service_name="speaker_diarization")

# Add as a router-level dependency so it runs before path-operation dependencies like get_speaker_diarization_service
inference_router.dependencies.append(Depends(enforce_speaker_diarization_checks))


@inference_router.post(
    "/inference",
    response_model=SpeakerDiarizationInferenceResponse,
    summary="Perform speaker diarization inference",
    description="Run speaker diarization on one or more audio files using Triton.",
)
async def run_inference(
    request_body: SpeakerDiarizationInferenceRequest,
    http_request: Request,
    speaker_diarization_service: SpeakerDiarizationService = Depends(
        get_speaker_diarization_service
    ),
) -> SpeakerDiarizationInferenceResponse:
    """
    Run speaker diarization inference for a batch of audio files.
    
    Creates detailed trace spans for the entire inference operation.
    """
    # Create a span for the entire inference operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _run_inference_impl(request_body, http_request, speaker_diarization_service)
    
    with tracer.start_as_current_span("speaker-diarization.inference") as span:
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
            span.set_attribute("speaker-diarization.audio_count", len(request_body.audio))
            span.set_attribute("speaker-diarization.service_id", request_body.config.serviceId if request_body.config else "unknown")
            
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
            span.add_event("speaker-diarization.inference.started", {
                "audio_count": len(request_body.audio),
                "service_id": request_body.config.serviceId if request_body.config else "unknown"
            })

            logger.info(
                "Processing Speaker Diarization inference request with %d audio file(s), user_id=%s api_key_id=%s session_id=%s",
                len(request_body.audio),
                user_id,
                api_key_id,
                session_id,
            )

            # Run inference (Triton + Speaker Diarization)
            response = await speaker_diarization_service.run_inference(
                request_body,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            
            # Add response metadata
            span.set_attribute("speaker-diarization.output_count", len(response.output))
            span.set_attribute("http.status_code", 200)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("speaker-diarization.inference.completed", {
                "output_count": len(response.output)
            })
            
            logger.info("Speaker Diarization inference completed successfully")
            return response

        except ValueError as exc:
            logger.warning("Validation error in Speaker Diarization inference: %s", exc)
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
        except TritonInferenceError as exc:
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
                    f"Triton inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                    "Please verify the model is registered in Model Management and the Triton server is accessible."
                )
            elif service_id:
                error_detail = (
                    f"Triton inference failed for serviceId '{service_id}': {error_detail}. "
                    "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
                )
            else:
                error_detail = (
                    f"Triton inference failed: {error_detail}. "
                    "Please ensure config.serviceId is provided and the service is registered in Model Management."
                )
            
            logger.error("Speaker Diarization Triton inference failed: %s (serviceId=%s, endpoint=%s)", 
                        exc, service_id, triton_endpoint)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_detail,
            ) from exc
        except Exception as exc:  # pragma: no cover - generic error path
            logger.error("Speaker Diarization inference failed: %s", exc, exc_info=True)
            if tracer:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", type(exc).__name__)
                    current_span.set_attribute("error.message", str(exc))
                    current_span.set_status(Status(StatusCode.ERROR, str(exc)))
                    current_span.record_exception(exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc


async def _run_inference_impl(
    request_body: SpeakerDiarizationInferenceRequest,
    http_request: Request,
    speaker_diarization_service: SpeakerDiarizationService
) -> SpeakerDiarizationInferenceResponse:
    """Fallback implementation when tracing is not available."""
    try:
        # Extract auth context from request.state (if middleware is configured)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        session_id = getattr(http_request.state, "session_id", None)

        logger.info(
            "Processing Speaker Diarization inference request with %d audio file(s), user_id=%s api_key_id=%s session_id=%s",
            len(request_body.audio),
            user_id,
            api_key_id,
            session_id,
        )

        # Run inference (Triton + Speaker Diarization)
        response = await speaker_diarization_service.run_inference(
            request_body,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        logger.info("Speaker Diarization inference completed successfully")
        return response

    except ValueError as exc:
        logger.warning("Validation error in Speaker Diarization inference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TritonInferenceError as exc:
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        error_detail = str(exc)
        
        # Include model management context in error message
        if service_id and triton_endpoint:
            error_detail = (
                f"Triton inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                "Please verify the model is registered in Model Management and the Triton server is accessible."
            )
        elif service_id:
            error_detail = (
                f"Triton inference failed for serviceId '{service_id}': {error_detail}. "
                "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
            )
        else:
            error_detail = (
                f"Triton inference failed: {error_detail}. "
                "Please ensure config.serviceId is provided and the service is registered in Model Management."
            )
        
        logger.error("Speaker Diarization Triton inference failed: %s (serviceId=%s, endpoint=%s)", 
                    exc, service_id, triton_endpoint)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail,
        ) from exc
    except Exception as exc:  # pragma: no cover - generic error path
        logger.error("Speaker Diarization inference failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc

