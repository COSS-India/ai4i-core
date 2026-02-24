"""
Inference router for NER service.

Exposes a ULCA-style NER inference endpoint:
- POST /api/v1/ner/inference
"""

import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id

from models.ner_request import NerInferenceRequest
from models.ner_response import NerInferenceResponse
from services.ner_service import NerService, TritonInferenceError
from repositories.ner_repository import NERRepository
from utils.triton_client import TritonClient
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session
from middleware.tenant_context import try_get_tenant_context
from sqlalchemy.ext.asyncio import AsyncSession
import os
import httpx
from middleware.exceptions import ErrorDetail
from fastapi import Depends

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("ner-service")

inference_router = APIRouter(
    prefix="/api/v1/ner",
    tags=["NER Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)

API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")


async def _enforce_tenant_and_service_checks(http_request: Request, service_name: str = "ner"):
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
                    accepted_names = {service_name.lower(), service_name.replace("-", "_").lower(), service_name.replace("_", "-").lower()}
                    if not any(name in subscriptions for name in accepted_names):
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
    # Multi-tenant endpoints only require Bearer token (not API key)
    # Create headers with only Authorization for multi-tenant service check
    service_check_headers = {}
    if headers and (headers.get("Authorization") or headers.get("authorization")):
        service_check_headers["Authorization"] = headers.get("Authorization") or headers.get("authorization")
    # Don't forward X-API-Key or X-Auth-Source for multi-tenant endpoints
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            svc_resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/list/services", headers=service_check_headers if service_check_headers else None)
            if svc_resp.status_code == 200:
                services = svc_resp.json().get("services", [])
                accepted_names = {service_name.lower(), service_name.replace("-", "_").lower(), service_name.replace("_", "-").lower()}
                svc_entry = next((s for s in services if str(s.get("service_name")).lower() in accepted_names), None)
                if not svc_entry or not svc_entry.get("is_active", False):
                    raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="NER service is not active at the moment. Please contact your administrator").dict())
            else:
                raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Cannot detect service availability. Please contact your administrator").dict())
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="NER service is temporarily unavailable. Please try again in a few minutes.").dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to verify service active state for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="NER service is temporarily unavailable. Please try again in a few minutes.").dict())

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


async def enforce_ner_checks(request: Request):
    """FastAPI dependency that enforces tenant and service checks for NER before other dependencies run."""
    # the service name is coming from multitenant SubscriptionType enum
    await _enforce_tenant_and_service_checks(request, service_name="ner")

# Add as a router-level dependency so it runs before path-operation dependencies like get_ner_service
inference_router.dependencies.append(Depends(enforce_ner_checks))


async def get_ner_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> NerService:
    """
    Dependency to construct NerService with configured Triton client and repository.

    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    repository = NERRepository(db)
    
    # Get middleware-resolved endpoint from Model Management database
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
                "NER service requires Model Management database resolution."
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
        f"Using endpoint={triton_endpoint} model_name={model_name} from Model Management "
        f"for serviceId={getattr(request.state, 'service_id', 'unknown')}"
    )
    
    # Create NER-specific TritonClient (has NER-specific methods like get_ner_io_for_triton)
    triton_client = TritonClient(triton_endpoint, triton_api_key or None)
    return NerService(repository=repository, triton_client=triton_client, model_name=model_name)


@inference_router.post(
    "/inference",
    response_model=NerInferenceResponse,
    summary="Perform batch NER inference",
    description="Run NER on one or more text inputs using Dhruva NER via Triton.",
    dependencies=[Depends(AuthProvider)],  # Explicitly enforce auth at endpoint level (in addition to router-level)
)
async def run_inference(
    request_body: NerInferenceRequest,
    http_request: Request,
    ner_service: NerService = Depends(get_ner_service),
) -> NerInferenceResponse:
    """
    Run NER inference for a batch of text inputs.
    
    Creates detailed trace spans for the entire inference operation.
    
    The Model Resolution Middleware automatically resolves serviceId from
    request_body.config.serviceId to triton_endpoint and model_name,
    which are available in http_request.state.
    """
    if not tracer:
        # Fallback if tracing not available
        return await _run_ner_inference_impl(request_body, http_request, ner_service)
    
    with tracer.start_as_current_span("ner.inference") as span:
        try:
            # -----------------------------
            # Authentication context span
            # -----------------------------
            with tracer.start_as_current_span("ner.auth_context") as auth_span:
                # Extract auth context from request.state (set by AuthProvider middleware)
                user_id = getattr(http_request.state, "user_id", None)
                api_key_id = getattr(http_request.state, "api_key_id", None)
                session_id = getattr(http_request.state, "session_id", None)

                # Header-level auth signals
                has_bearer_header = bool(http_request.headers.get("authorization"))
                has_api_key_header = "x-api-key" in {k.lower(): v for k, v in http_request.headers.items()}

                auth_span.set_attribute("auth.user_id", str(user_id) if user_id is not None else "")
                auth_span.set_attribute("auth.api_key_id", str(api_key_id) if api_key_id is not None else "")
                auth_span.set_attribute("auth.session_id", str(session_id) if session_id is not None else "")
                auth_span.set_attribute("auth.has_bearer_header", has_bearer_header)
                auth_span.set_attribute("auth.has_api_key_header", has_api_key_header)
                auth_span.set_attribute(
                    "auth.is_authenticated",
                    bool(user_id is not None or api_key_id is not None),
                )
            
            # Get correlation ID for log/trace correlation (shared across auth + inference)
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)

            # Add request metadata to span
            span.set_attribute("ner.input_count", len(request_body.input))
            span.set_attribute("ner.service_id", request_body.config.serviceId)
            span.set_attribute("ner.language", request_body.config.language.sourceLanguage)
            
            # Track request size (approximate)
            try:
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
            span.add_event("ner.inference.started", {
                "input_count": len(request_body.input),
                "service_id": request_body.config.serviceId,
                "language": request_body.config.language.sourceLanguage
            })

            logger.info(
                "Processing NER inference request with %d text input(s), "
                "user_id=%s api_key_id=%s session_id=%s",
                len(request_body.input),
                user_id,
                api_key_id,
                session_id,
            )

            response = await ner_service.run_inference(
                request_body,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            
            # Add response metadata
            span.set_attribute("ner.output_count", len(response.output))
            span.set_attribute("http.status_code", 200)
            
            # Track response size (approximate)
            try:
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("ner.inference.completed", {
                "output_count": len(response.output),
                "status": "success"
            })
            span.set_status(Status(StatusCode.OK))
            logger.info("NER inference completed successfully")
            return response

        except ValueError as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("ner.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Validation error in NER inference: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except TritonInferenceError as exc:
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 503)
            if service_id:
                span.set_attribute("ner.service_id", service_id)
            if triton_endpoint:
                span.set_attribute("triton.endpoint", triton_endpoint)
            if model_name:
                span.set_attribute("triton.model_name", model_name)
            span.add_event("ner.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            
            error_detail = (
                f"NER inference failed for serviceId '{service_id}' "
                f"at endpoint '{triton_endpoint}' with model '{model_name}': {str(exc)}. "
                "Please verify the model is registered in Model Management and the Triton server is accessible."
            )
            
            logger.error(
                "NER Triton inference failed: %s (serviceId=%s, endpoint=%s, model=%s)",
                exc, service_id, triton_endpoint, model_name
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_detail,
            ) from exc
        except Exception as exc:  # pragma: no cover - generic error path
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 500)
            if service_id:
                span.set_attribute("ner.service_id", service_id)
            if triton_endpoint:
                span.set_attribute("triton.endpoint", triton_endpoint)
            if model_name:
                span.set_attribute("triton.model_name", model_name)
            span.add_event("ner.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            
            error_detail = str(exc)
            
            # Include model management context in error message
            if service_id and triton_endpoint:
                error_detail = (
                    f"NER inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                    "Please verify the model is registered in Model Management and the Triton server is accessible."
                )
            elif service_id:
                error_detail = (
                    f"NER inference failed for serviceId '{service_id}': {error_detail}. "
                    "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
                )
            else:
                error_detail = (
                    f"NER inference failed: {error_detail}. "
                    "Please ensure config.serviceId is provided and the service is registered in Model Management."
                )
            
            logger.error(
                "NER inference failed: %s (serviceId=%s, endpoint=%s)",
                exc, service_id, triton_endpoint, exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            ) from exc


async def _run_ner_inference_impl(
    request_body: NerInferenceRequest,
    http_request: Request,
    ner_service: NerService,
) -> NerInferenceResponse:
    """Fallback implementation when tracing is not available."""
    # Extract auth context from request.state (if middleware is configured)
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    logger.info(
        "Processing NER inference request with %d text input(s), "
        "user_id=%s api_key_id=%s session_id=%s",
        len(request_body.input),
        user_id,
        api_key_id,
        session_id,
    )

    response = await ner_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id
    )
    logger.info("NER inference completed successfully")
    return response



