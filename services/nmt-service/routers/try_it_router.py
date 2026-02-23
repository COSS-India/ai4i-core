"""
Try-It Router
FastAPI router for anonymous try-it endpoint (migrated from API gateway)
"""
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.nmt_request import TryItRequest, NMTInferenceRequest
from models.nmt_response import NMTInferenceResponse
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session
from utils.try_it_utils import (
    get_try_it_key,
    increment_try_it_count,
    is_try_it_rate_limit_exceeded
)
from routers.inference_router import (
    resolve_service_id_if_needed,
    get_nmt_service
)
from utils.auth_utils import extract_auth_headers

logger = logging.getLogger(__name__)

# Create router
try_it_router = APIRouter(
    prefix="/api/v1",
    tags=["Try It"],
    # Note: AuthProvider is optional for try-it - it will handle /api/v1/try-it path
    dependencies=[Depends(AuthProvider)]
)


@try_it_router.post(
    "/try-it",
    response_model=Dict[str, Any],
    summary="Anonymous Try-It access for NMT",
    description="Allows anonymous users to try NMT service with rate limiting. Only NMT service is supported."
)
async def try_it_inference(
    payload: TryItRequest,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session)
) -> Dict[str, Any]:
    """
    Anonymous Try-It access. Only NMT is allowed; others require login.
    
    This endpoint supports:
    - Anonymous access with rate limiting (5 requests per hour per session/IP)
    - API key authentication (bypasses rate limiting)
    - JWT authentication (bypasses rate limiting)
    """
    # Validate service name
    service_name = payload.service_name.strip().lower()
    if service_name not in {"nmt", "nmt-service"}:
        raise HTTPException(
            status_code=403,
            detail="Please login to access other services."
        )
    
    # Check if user is authenticated (has API key or JWT)
    # If authenticated, bypass rate limiting
    is_authenticated = getattr(request.state, "is_authenticated", False)
    user_id = getattr(request.state, "user_id", None)
    api_key_id = getattr(request.state, "api_key_id", None)
    
    # Apply rate limiting only for anonymous users
    if not is_authenticated:
        # Get Redis client from app state
        redis_client = getattr(request.app.state, "redis_client", None)
        
        # Get rate limiting key
        key = get_try_it_key(request)
        
        # Increment counter
        count = await increment_try_it_count(key, redis_client)
        
        # Check rate limit
        if is_try_it_rate_limit_exceeded(count):
            logger.warning(
                "Try-it rate limit exceeded",
                extra={
                    "key": key,
                    "count": count,
                    "limit": 5,
                    "client_ip": request.client.host if request.client else "unknown"
                }
            )
            raise HTTPException(
                status_code=403,
                detail="Please login to access other services."
            )
        
        logger.info(
            "Try-it request (anonymous)",
            extra={
                "key": key,
                "count": count,
                "limit": 5,
                "client_ip": request.client.host if request.client else "unknown"
            }
        )
    else:
        logger.info(
            "Try-it request (authenticated)",
            extra={
                "user_id": user_id,
                "api_key_id": api_key_id,
                "bypass_rate_limit": True
            }
        )
    
    # Convert payload to NMTInferenceRequest
    try:
        nmt_request = NMTInferenceRequest(**payload.payload)
    except Exception as e:
        logger.error(f"Failed to parse try-it payload: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid payload format: {str(e)}"
        )
    
    # For anonymous try-it requests, set a default service ID if not provided
    # This avoids calling SMR which might require authentication
    if not is_authenticated and not nmt_request.config.serviceId:
        # Use default IndicTrans service for anonymous users (same as frontend)
        default_service_id = "ai4bharat/indictrans--gpu-t4"
        nmt_request.config.serviceId = default_service_id
        logger.info(
            "Try-it: Using default service ID for anonymous user",
            extra={"service_id": default_service_id}
        )
    
    # Set serviceId in request state
    request.state.service_id = nmt_request.config.serviceId
    
    # For try-it requests, manually resolve the endpoint from Model Management
    # The middleware can't find serviceId because it's nested in payload.config.serviceId
    # Model Management client will use fallback API key automatically when no auth headers are present
    model_management_client = getattr(request.app.state, "model_management_client", None)
    redis_client = getattr(request.app.state, "redis_client", None)
    
    if model_management_client and nmt_request.config.serviceId:
        try:
            # Call Model Management with X-Try-It header to allow anonymous access
            # Model Management service will allow anonymous access when X-Try-It header is present
            auth_headers = {"X-Try-It": "true"}  # This allows anonymous access in Model Management
            service_info = await model_management_client.get_service(
                service_id=nmt_request.config.serviceId,
                use_cache=True,
                redis_client=redis_client,
                auth_headers=auth_headers,
            )
            
            if service_info and service_info.endpoint:
                # Set endpoint in request state so get_nmt_service can use it
                request.state.triton_endpoint = service_info.endpoint
                request.state.triton_api_key = service_info.api_key or ""
                
                # Extract model name
                triton_model_name = "unknown"
                if service_info.model_inference_endpoint:
                    inference_endpoint = service_info.model_inference_endpoint
                    if isinstance(inference_endpoint, dict):
                        triton_model_name = (
                            inference_endpoint.get("model_name") or
                            inference_endpoint.get("modelName") or
                            inference_endpoint.get("model") or
                            service_info.triton_model or
                            service_info.model_name or
                            "unknown"
                        )
                elif service_info.model_name:
                    triton_model_name = service_info.model_name
                elif service_info.triton_model:
                    triton_model_name = service_info.triton_model
                
                request.state.triton_model_name = triton_model_name
                
                logger.info(
                    "Try-it: Resolved endpoint from Model Management",
                    extra={
                        "service_id": nmt_request.config.serviceId,
                        "triton_endpoint": service_info.endpoint,
                        "triton_model_name": triton_model_name,
                    }
                )
            else:
                logger.warning(
                    "Try-it: Service not found in Model Management or has no endpoint",
                    extra={"service_id": nmt_request.config.serviceId}
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "ENDPOINT_RESOLUTION_FAILED",
                        "message": f"Service {nmt_request.config.serviceId} not found in Model Management or has no endpoint configured.",
                        "service_id": nmt_request.config.serviceId,
                    }
                )
        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Try-it: Failed to resolve endpoint from Model Management",
                extra={
                    "service_id": nmt_request.config.serviceId,
                    "error": error_msg,
                    "error_type": type(e).__name__,
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "ENDPOINT_RESOLUTION_FAILED",
                    "message": f"Failed to resolve endpoint for serviceId {nmt_request.config.serviceId}: {error_msg}",
                    "service_id": nmt_request.config.serviceId,
                }
            ) from e
    
    # Call the inference endpoint logic
    # We need to manually set up the dependencies
    # For authenticated users or if serviceId is provided, try SMR
    # For anonymous users with default serviceId, skip SMR
    smr_response = None
    if is_authenticated:
        try:
            smr_response = await resolve_service_id_if_needed(nmt_request, request)
        except Exception as e:
            logger.warning(
                f"SMR call failed for try-it request, continuing with provided serviceId: {e}",
                exc_info=True
            )
            # If SMR fails, continue with the serviceId that was provided or set
            smr_response = None
    
    nmt_service = await get_nmt_service(request, db)
    
    # Check if SMR returned a context-aware result
    if smr_response and smr_response.get("context_aware_result"):
        logger.info(
            "Try-it: Using context-aware result from SMR",
            extra={
                "context": {
                    "user_id": getattr(request.state, "user_id", None),
                    "tenant_id": getattr(request.state, "tenant_id", None),
                }
            }
        )
        
        # SMR already handled the context-aware translation, return the result
        from models.nmt_response import TranslationOutput
        context_output = smr_response.get("context_aware_result", {}).get("output", [])
        output_list = [
            TranslationOutput(
                source=item.get("source", ""),
                target=item.get("target", "")
            )
            for item in context_output
        ]
        
        response = NMTInferenceResponse(output=output_list, smr_response=smr_response)
        return response.dict()
    
    # Extract auth context from request.state
    user_id = getattr(request.state, "user_id", None)
    api_key_id = getattr(request.state, "api_key_id", None)
    session_id = getattr(request.state, "session_id", None)
    
    # Run inference using the NMT service directly
    # This matches the logic in inference_router.run_inference
    response = await nmt_service.run_inference(
        request=nmt_request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
        auth_headers=extract_auth_headers(request),
        http_request=request,
    )
    
    # Include SMR response if available
    response_dict = response.dict()
    if smr_response:
        response_dict["smr_response"] = smr_response
    else:
        response_dict["smr_response"] = None
    
    # Return response as dict (matching API gateway format)
    return response_dict
