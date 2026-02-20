"""
Inference Router
FastAPI router for LLM inference endpoints
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.llm_request import LLMInferenceRequest
from models.llm_response import LLMInferenceResponse
from repositories.llm_repository import LLMRepository
from services.llm_service import LLMService
from utils.triton_client import TritonClient
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session
import os
import httpx
from middleware.exceptions import ErrorDetail
from fastapi import Depends


# API Gateway URL for multi-tenant checks
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")


logger = logging.getLogger(__name__)

# Create router
inference_router = APIRouter(
    prefix="/api/v1/llm",
    tags=["LLM Inference"],
    dependencies=[Depends(AuthProvider)]
)



async def get_llm_service(request: Request, db: AsyncSession = Depends(get_tenant_db_session)) -> LLMService:
    """Dependency to get configured LLM service"""
    repository = LLMRepository(db)
    triton_client = TritonClient(
        triton_url=request.app.state.triton_endpoint,
        api_key=request.app.state.triton_api_key,
        timeout=getattr(request.app.state, 'triton_timeout', 300.0)
    )
    return LLMService(repository, triton_client)


async def _enforce_tenant_and_service_checks(http_request: Request, service_name: str = "llm"):
    """
    Enforce tenant subscription, tenant status (ACTIVE) and global service active flag.
    Execution order:
      1) If tenant context exists, ensure tenant subscribes to this service
      2) Ensure the service is globally active via /list/services
      3) If tenant context exists, ensure tenant.status == ACTIVE
    """
    headers = {}
    auth_header = http_request.headers.get("Authorization") or http_request.headers.get("authorization")
    if auth_header:
        headers["Authorization"] = auth_header
                
    x_api_key = http_request.headers.get("X-API-Key") or http_request.headers.get("x-api-key")
    if x_api_key:
        headers["X-API-Key"] = x_api_key

    x_auth_source = http_request.headers.get("X-Auth-Source") or http_request.headers.get("x-auth-source")
    if x_auth_source:
        headers["x-auth-source"] = x_auth_source

    # If tenant context exists, ensure tenant is subscribed to the service FIRST
    tenant_id = getattr(http_request.state, "tenant_id", None)
    tenant_data = None
    if tenant_id:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                client_resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/admin/view/tenant", params={"tenant_id": tenant_id}, headers=headers)
                if client_resp.status_code == 200:
                    tenant_data = client_resp.json()
                    subscriptions = [str(s).lower() for s in (tenant_data.get("subscriptions") or [])]
                    if service_name.lower() not in subscriptions:
                        raise HTTPException(
                            status_code=403,
                            detail={"code": "SERVICE_NOT_SUBSCRIBED", "message": f"Tenant '{tenant_id}' is not subscribed to '{service_name}'"},
                        )
                elif client_resp.status_code == 404:
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
            svc_resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/list/services", headers=headers)
            if svc_resp.status_code == 200:
                services = svc_resp.json().get("services", [])
                svc_entry = next((s for s in services if str(s.get("service_name")).lower() == service_name.lower()), None)
                if not svc_entry or not svc_entry.get("is_active", False):
                    raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="LLM service is not active at the moment. Please contact your administrator").dict())
            else:
                raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="Cannot detect service availability. Please contact your administrator").dict())
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="LLM service is temporarily unavailable. Please try again in a few minutes.").dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to verify service active state for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=ErrorDetail(code="SERVICE_UNAVAILABLE", message="LLM service is temporarily unavailable. Please try again in a few minutes.").dict())

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


async def enforce_llm_checks(request: Request):
    """FastAPI dependency that enforces tenant and service checks for LLM before other dependencies run."""
    # the service name is coming from multitenant SubscriptionType enum
    await _enforce_tenant_and_service_checks(request, service_name="llm")

# Add as a router-level dependency so it runs before path-operation dependencies like get_llm_service
inference_router.dependencies.insert(0, Depends(enforce_llm_checks))


@inference_router.post(
    "/inference",
    response_model=LLMInferenceResponse,
    summary="Perform LLM inference",
    description="Process text using LLM for language processing (translation, generation, etc.)"
)
async def run_inference(
    request: LLMInferenceRequest,
    http_request: Request,
    llm_service: LLMService = Depends(get_llm_service)
) -> LLMInferenceResponse:
    """Run LLM inference on the given request"""
    try:
        # Extract auth context from request.state
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_id = getattr(http_request.state, 'api_key_id', None)
        session_id = getattr(http_request.state, 'session_id', None)
        
        # Log incoming request
        logger.info(f"Processing LLM inference request with {len(request.input)} texts")
        
        # Run inference
        response = await llm_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        
        logger.info(f"LLM inference completed successfully")
        return response
        
    except Exception as e:
        logger.error(f"LLM inference failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available LLM models",
    description="Get list of supported LLM models",
    dependencies=[Depends(AuthProvider)]
)
async def list_models() -> Dict[str, Any]:
    """List available LLM models"""
    return {
        "models": [
            {
                "model_id": "llm",
                "provider": "AI4Bharat",
                "description": "LLM model for text processing, translation, and generation",
                "max_batch_size": 100,
                "supported_languages": ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or", "as", "ur"]
            }
        ],
        "total_models": 1
    }

