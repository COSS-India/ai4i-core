"""
Pipeline router for Pipeline Service

FastAPI router for pipeline inference endpoints.
Includes distributed tracing for end-to-end observability.
"""

import logging
import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from models.pipeline_request import PipelineInferenceRequest
from models.pipeline_response import PipelineInferenceResponse
from services.pipeline_service import PipelineService
from utils.http_client import ServiceClient
from middleware.auth_provider import AuthProvider
from middleware.exceptions import (
    PipelineError,
    PipelineTaskError,
    ServiceUnavailableError,
    ModelNotFoundError,
    ErrorDetail,
    AuthenticationError
)
import os
import httpx
from middleware.tenant_context import try_get_tenant_context

# API Gateway URL for multi-tenant checks
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")

# Import OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from ai4icore_logging import get_correlation_id
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logging.warning("OpenTelemetry not available, tracing disabled in router")
    def get_correlation_id(request):
        return None

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("pipeline-service") if TRACING_AVAILABLE else None

# Create router
pipeline_router = APIRouter(
    prefix="/api/v1/pipeline",
    tags=["Pipeline"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


def get_service_client() -> ServiceClient:
    """Dependency to get service client."""
    return ServiceClient()


def get_pipeline_service() -> PipelineService:
    """Dependency to get pipeline service instance."""
    service_client = get_service_client()
    return PipelineService(service_client)



async def _enforce_tenant_and_service_checks(http_request: Request, service_name: str = "pipeline"):
    """
    Enforce tenant subscription, tenant status (ACTIVE) and global service active flag.
    Execution order:
      1) If tenant context exists, ensure tenant subscribes to this service
      2) Ensure the service is globally active via /api/v1/multi-tenant/list/services
      3) If tenant context exists, ensure tenant.status == ACTIVE
    """
    # Build headers to forward
    auth_header = http_request.headers.get("Authorization") or http_request.headers.get("authorization")
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
                    # Accept multiple enum variants for pipeline services (e.g., "pipeline", "speech_to_speech_pipeline")
                    accepted_names = {service_name.lower()}
                    if service_name.lower() == "pipeline":
                        accepted_names.add("speech_to_speech_pipeline")
                    if not any(name in subscriptions for name in accepted_names):
                        raise HTTPException(
                            status_code=403,
                            detail={"code": "SERVICE_NOT_SUBSCRIBED", "message": f"Tenant '{tenant_id}' is not subscribed to '{service_name}'"},
                        )
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
                # Accept multiple enum variants for pipeline service registration
                accepted_names = {service_name.lower()}
                if service_name.lower() == "pipeline":
                    accepted_names.add("speech_to_speech_pipeline")
                svc_entry = next((s for s in services if str(s.get("service_name")).lower() in accepted_names), None)
                if not svc_entry or not svc_entry.get("is_active", False):
                    raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Speech to speech pipeline service is not active at the moment. Please contact your administrator").dict())
            else:
                raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Cannot detect service availability. Please contact your administrator").dict())
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Speech to speech pipeline service is temporarily unavailable. Please try again in a few minutes.").dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to verify service active state for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Speech to speech pipeline service is temporarily unavailable. Please try again in a few minutes.").dict())

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


async def enforce_pipeline_checks(request: Request):
    """FastAPI dependency that enforces tenant and service checks for Pipeline before other dependencies run."""
    # the service name is coming from multitenant SubscriptionType enum
    await _enforce_tenant_and_service_checks(request, service_name="pipeline")

# Add as a router-level dependency so it runs before path-operation dependencies like get_pipeline_service
pipeline_router.dependencies.append(Depends(enforce_pipeline_checks))


@pipeline_router.post(
    "/inference",
    response_model=PipelineInferenceResponse,
    summary="Execute pipeline inference",
    description="Execute a multi-task AI pipeline (e.g., Speech-to-Speech translation)"
)
async def run_pipeline_inference(
    request: PipelineInferenceRequest,
    http_request: Request
) -> PipelineInferenceResponse:
    """
    Execute a pipeline of AI tasks.
    
    Creates detailed trace spans for the entire pipeline operation.
    Example: ASR → Translation → TTS for Speech-to-Speech translation
    """
    # Create a span for the entire pipeline operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _execute_pipeline_request(request, http_request, None, None)
    
    with tracer.start_as_current_span("pipeline.inference") as span:
        try:
            # Extract auth context from request.state (if middleware is configured)
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            
            # Get correlation ID for log/trace correlation
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)
            
            # Add request metadata to span
            span.set_attribute("pipeline.task_count", len(request.pipelineTasks))
            task_types = [task.taskType.value for task in request.pipelineTasks]
            span.set_attribute("pipeline.task_types", ",".join(task_types))
            span.set_attribute("pipeline.has_input_data", hasattr(request, 'inputData') and request.inputData is not None)
            
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
            
            # Add span event for request start
            span.add_event("pipeline.inference.started", {
                "task_count": len(request.pipelineTasks),
                "task_types": ",".join(task_types)
            })
            
            logger.info(
                "Processing pipeline inference request with %d tasks, user_id=%s api_key_id=%s",
                len(request.pipelineTasks),
                user_id,
                api_key_id
            )
            
            # Execute pipeline
            response = await _execute_pipeline_request(request, http_request, tracer, span)
            
            # Add response metadata
            span.set_attribute("http.status_code", 200)
            span.set_attribute("pipeline.success", True)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("pipeline.inference.completed", {
                "status": "success",
                "task_count": len(request.pipelineTasks)
            })
            span.set_status(Status(StatusCode.OK))
            logger.info("Pipeline inference completed successfully")
            return response
            
        except AuthenticationError:
            # Re-raise authentication errors as-is so they're handled by the error handler
            raise
        except (PipelineTaskError, ModelNotFoundError, ServiceUnavailableError) as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("pipeline.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Pipeline error: %s", exc)
            raise
            
        except Exception as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 500)
            span.add_event("pipeline.inference.exception", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.error("Unexpected error in pipeline inference: %s", exc, exc_info=True)
            raise


async def _execute_pipeline_request(
    request: PipelineInferenceRequest,
    http_request: Request,
    tracer,
    root_span
) -> PipelineInferenceResponse:
    """Internal pipeline request execution logic."""
    # Extract JWT token and API key from request headers
    jwt_token = None
    api_key = None
    
    auth_header = http_request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        jwt_token = auth_header.replace('Bearer ', '')
    
    api_key_header = http_request.headers.get('X-API-Key')
    if api_key_header:
        api_key = api_key_header
    
    # Extract user_id from request state (set by AuthProvider middleware)
    # This is needed for tenant routing in downstream services (ASR, NMT, TTS)
    user_id = getattr(http_request.state, "user_id", None)
    
    logger.info(f"🔐 Authentication extracted: JWT={'present' if jwt_token else 'absent'}, API_KEY={'present' if api_key else 'absent'}, USER_ID={user_id}")
    
    # Get pipeline service
    pipeline_service = get_pipeline_service()
    
    # Execute pipeline (this will create its own spans)
    response = await pipeline_service.run_pipeline_inference(
        request=request,
        jwt_token=jwt_token,
        api_key=api_key,
        user_id=user_id
    )
    
    logger.info("✅ Pipeline inference completed successfully")
    return response


@pipeline_router.get(
    "/info",
    summary="Pipeline service information",
    description="Get pipeline service capabilities and usage information"
)
async def get_pipeline_info() -> Dict[str, Any]:
    """Get pipeline service information."""
    return {
        "service": "pipeline-service",
        "version": "1.0.0",
        "description": "Multi-task AI pipeline orchestration service",
        "supported_task_types": ["asr", "translation", "tts", "transliteration"],
        "example_pipelines": {
            "speech_to_speech": {
                "description": "Full Speech-to-Speech translation pipeline",
                "tasks": [
                    {
                        "taskType": "asr",
                        "description": "Convert audio to text"
                    },
                    {
                        "taskType": "translation",
                        "description": "Translate text"
                    },
                    {
                        "taskType": "tts",
                        "description": "Convert text to speech"
                    }
                ]
            },
            "text_to_speech": {
                "description": "Text translation to speech pipeline",
                "tasks": [
                    {
                        "taskType": "translation",
                        "description": "Translate text"
                    },
                    {
                        "taskType": "tts",
                        "description": "Convert text to speech"
                    }
                ]
            }
        },
        "task_sequence_rules": {
            "asr": ["translation"],
            "translation": ["tts"],
            "transliteration": ["translation", "tts"]
        }
    }
