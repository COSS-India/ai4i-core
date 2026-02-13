"""
Inference Router
FastAPI router for NMT inference endpoints
"""

import logging
import os
import time
from typing import Dict, Any, Optional

import httpx
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

# SMR Service Configuration
SMR_SERVICE_URL = os.getenv("SMR_SERVICE_URL", "http://smr-service:8097")

# Create router
inference_router = APIRouter(
    prefix="/api/v1/nmt",
    tags=["NMT Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session (legacy - use get_tenant_db_session for tenant routing)"""
    return request.app.state.db_session_factory()


async def resolve_service_id_if_needed(
    request: NMTInferenceRequest,
    http_request: Request,
) -> Optional[Dict[str, Any]]:
    """
    Dependency to resolve serviceId via SMR if not provided in request.
    This runs before get_nmt_service to ensure serviceId is available.
    
    Returns SMR response data if SMR was called, None otherwise.
    """
    logger.info(
        "resolve_service_id_if_needed dependency called",
        extra={
            "has_service_id": bool(request.config.serviceId),
            "service_id": request.config.serviceId,
        }
    )
    
    # Check if serviceId is missing
    if not request.config.serviceId:
        user_id = getattr(http_request.state, "user_id", None)
        
        # Only use tenant_id if it's from JWT token, not from fallback lookup
        # Check if tenant_id exists in JWT payload (authentic tenant_id)
        jwt_payload = getattr(http_request.state, "jwt_payload", None)
        tenant_id_from_jwt = None
        if jwt_payload:
            tenant_id_from_jwt = jwt_payload.get("tenant_id")
        
        # Only pass tenant_id to SMR if it's from JWT token
        # If tenant_id is from fallback lookup (not in JWT), treat as free user
        tenant_id = tenant_id_from_jwt if tenant_id_from_jwt else None
        
        logger.info(
            "serviceId not provided, calling SMR service (dependency)",
            extra={
                "user_id": user_id,
                "tenant_id_from_jwt": tenant_id_from_jwt,
                "tenant_id_passed_to_smr": tenant_id,
            }
        )
        
        # Call SMR service to get serviceId
        # Use model_dump() or dict() with exclude_none=False to preserve all fields including context
        try:
            # Try model_dump() first (Pydantic v2)
            request_body = request.model_dump(exclude_none=False)
        except AttributeError:
            # Fallback to dict() (Pydantic v1)
            request_body = request.dict(exclude_none=False)
        
        # Debug: Log context field to verify it's being passed
        context_value = request_body.get("config", {}).get("context") if isinstance(request_body.get("config"), dict) else None
        logger.info(
            "Preparing SMR request with context",
            extra={
                "has_context": context_value is not None,
                "context_value": str(context_value)[:100] if context_value else None,
                "config_keys": list(request_body.get("config", {}).keys()) if isinstance(request_body.get("config"), dict) else None,
            }
        )
        
        smr_response_data = await call_smr_service(
            request_body=request_body,
            user_id=str(user_id) if user_id else None,
            tenant_id=str(tenant_id) if tenant_id else None,
            http_request=http_request,
        )
        
        # Update request with serviceId from SMR
        service_id = smr_response_data.get("serviceId")
        if not service_id:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "SMR_NO_SERVICE_ID",
                    "message": "SMR service did not return a serviceId",
                },
            )
        
        # Check if this is a context-aware result - if so, skip endpoint resolution
        context_aware_result = smr_response_data.get("context_aware_result")
        if context_aware_result or service_id == "llm_context_aware":
            logger.info(
                "Context-aware result from SMR, skipping endpoint resolution and Triton calls",
                extra={
                    "service_id": service_id,
                    "has_context_aware_result": bool(context_aware_result),
                }
            )
            # Store SMR response and skip endpoint resolution
            http_request.state.smr_response_data = smr_response_data
            request.config.serviceId = service_id
            http_request.state.service_id = service_id
            # Mark that this is context-aware so we don't try to resolve endpoints or call Triton
            http_request.state.is_context_aware = True
            return smr_response_data
        
        request.config.serviceId = service_id
        # Also set in request.state for Model Management middleware
        http_request.state.service_id = service_id
        
        # Manually resolve Triton endpoint using Model Management client
        # (since middleware already ran and didn't see serviceId)
        model_management_client = getattr(http_request.app.state, "model_management_client", None)
        redis_client = getattr(http_request.app.state, "redis_client", None)
        
        if not model_management_client:
            logger.error(
                "Model Management client not available in app.state - cannot resolve endpoint",
                extra={"service_id": service_id}
            )
            http_request.state.model_management_error = "Model Management client not available in application state"
        else:
            try:
                auth_headers = extract_auth_headers(http_request)
                # Get service info from Model Management
                service_info = await model_management_client.get_service(
                    service_id=service_id,
                    use_cache=True,
                    redis_client=redis_client,
                    auth_headers=auth_headers,
                )
                
                if not service_info:
                    logger.error(
                        "Service not found in Model Management",
                        extra={"service_id": service_id}
                    )
                    http_request.state.model_management_error = f"Service {service_id} not found in Model Management database"
                elif not service_info.endpoint:
                    logger.error(
                        "Service found but has no endpoint configured",
                        extra={
                            "service_id": service_id,
                            "service_name": service_info.name,
                            "model_id": service_info.model_id,
                        }
                    )
                    http_request.state.model_management_error = f"Service {service_id} found but has no endpoint configured"
                else:
                    triton_endpoint = service_info.endpoint
                    triton_api_key = service_info.api_key or ""
                    
                    # Extract model name from inference endpoint
                    # The model_name is typically stored in model_inference_endpoint.model_name
                    triton_model_name = "unknown"
                    if service_info.model_inference_endpoint:
                        # Try to extract model name from inference endpoint schema
                        inference_endpoint = service_info.model_inference_endpoint
                        if isinstance(inference_endpoint, dict):
                            # Check common patterns for model name in inference endpoint
                            # model_name is the standard field name in InferenceEndPoint
                            triton_model_name = (
                                inference_endpoint.get("model_name") or
                                inference_endpoint.get("modelName") or
                                inference_endpoint.get("model") or
                                service_info.triton_model or
                                service_info.model_name or
                                "unknown"
                            )
                            logger.debug(
                                "Extracted model name from inference endpoint",
                                extra={
                                    "service_id": service_id,
                                    "model_name": triton_model_name,
                                    "inference_endpoint_keys": list(inference_endpoint.keys()) if isinstance(inference_endpoint, dict) else None,
                                }
                            )
                    elif service_info.model_name:
                        triton_model_name = service_info.model_name
                    elif service_info.triton_model:
                        triton_model_name = service_info.triton_model
                    
                    http_request.state.triton_endpoint = triton_endpoint
                    http_request.state.triton_api_key = triton_api_key
                    http_request.state.triton_model_name = triton_model_name
                    logger.info(
                        "Manually resolved Triton endpoint for SMR-selected serviceId",
                        extra={
                            "service_id": service_id,
                            "triton_endpoint": triton_endpoint,
                            "triton_model_name": triton_model_name,
                            "has_api_key": bool(triton_api_key),
                        }
                    )
            except Exception as e:
                logger.error(
                    "Error resolving Triton endpoint for SMR-selected serviceId",
                    extra={"service_id": service_id, "error": str(e)},
                    exc_info=True
                )
                # Set error in request state so get_nmt_service can provide better error message
                http_request.state.model_management_error = str(e)
                # Re-raise if it's a critical error that should stop processing
                if "401" in str(e) or "403" in str(e) or "404" in str(e):
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "code": "MODEL_MANAGEMENT_ERROR",
                            "message": f"Failed to resolve endpoint for serviceId {service_id}: {str(e)}",
                        },
                    ) from e
        
        # Store SMR response in request state for later use
        http_request.state.smr_response_data = smr_response_data
        
        # Verify that endpoint was set (if Model Management client was available)
        # Skip this check if context-aware was used (endpoint resolution was skipped)
        is_context_aware = getattr(http_request.state, "is_context_aware", False)
        if not is_context_aware and model_management_client:
            triton_endpoint_check = getattr(http_request.state, "triton_endpoint", None)
            if not triton_endpoint_check:
                model_mgmt_error = getattr(http_request.state, "model_management_error", None)
                error_msg = f"Failed to resolve Triton endpoint for serviceId: {service_id}"
                if model_mgmt_error:
                    error_msg += f". {model_mgmt_error}"
                else:
                    error_msg += ". Please ensure the service is registered in Model Management database with a valid endpoint."
                
                logger.error(
                    "Failed to resolve Triton endpoint after SMR call",
                    extra={
                        "service_id": service_id,
                        "model_management_error": model_mgmt_error,
                    }
                )
                # Include SMR response in error if SMR was called
                error_detail = {
                    "code": "ENDPOINT_RESOLUTION_FAILED",
                    "message": error_msg,
                }
                if smr_response_data:
                    error_detail["smr_response"] = smr_response_data
                raise HTTPException(
                    status_code=500,
                    detail=error_detail,
                )
        
        logger.info(
            "SMR service returned serviceId, updated request (dependency)",
            extra={
                "service_id": request.config.serviceId,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "endpoint_resolved": bool(getattr(http_request.state, "triton_endpoint", None)),
            }
        )
        
        return smr_response_data
    
    return None


async def call_smr_service(
    request_body: Dict[str, Any],
    user_id: Optional[str],
    tenant_id: Optional[str],
    http_request: Request,
) -> Dict[str, Any]:
    """
    Call SMR service to get serviceId for the request.
    
    Args:
        request_body: The NMT inference request body as a dictionary
        user_id: User ID from auth context
        tenant_id: Tenant ID from request state
        http_request: FastAPI Request object for extracting headers
        
    Returns:
        SMR response dictionary containing serviceId and policy metadata
    """
    try:
        # Extract policy headers from the incoming request
        headers = dict(http_request.headers)
        latency_policy = headers.get("X-Latency-Policy") or headers.get("x-latency-policy")
        cost_policy = headers.get("X-Cost-Policy") or headers.get("x-cost-policy")
        accuracy_policy = headers.get("X-Accuracy-Policy") or headers.get("x-accuracy-policy")
        
        # Prepare SMR request payload
        smr_payload = {
            "task_type": "nmt",
            "request_body": request_body,
            "user_id": str(user_id) if user_id else None,
            "tenant_id": str(tenant_id) if tenant_id else None,
        }
        
        # Prepare headers for SMR call (forward auth headers, policy headers, and context-aware header)
        smr_headers = {}
        if "Authorization" in headers:
            smr_headers["Authorization"] = headers["Authorization"]
        if "X-API-Key" in headers:
            smr_headers["X-API-Key"] = headers["X-API-Key"]
        if latency_policy:
            smr_headers["X-Latency-Policy"] = latency_policy
        if cost_policy:
            smr_headers["X-Cost-Policy"] = cost_policy
        if accuracy_policy:
            smr_headers["X-Accuracy-Policy"] = accuracy_policy
        # Forward context-aware header to SMR
        context_aware_header = headers.get("X-Context-Aware") or headers.get("x-context-aware")
        if context_aware_header:
            smr_headers["X-Context-Aware"] = context_aware_header
        
        logger.info(
            "Calling SMR service to get serviceId",
            extra={
                "user_id": user_id,
                "tenant_id": tenant_id,
                "has_policy_headers": bool(latency_policy or cost_policy or accuracy_policy),
            }
        )
        
        # Call SMR service
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{SMR_SERVICE_URL}/api/v1/smr/select-service",
                json=smr_payload,
                headers=smr_headers,
            )
            response.raise_for_status()
            smr_response = response.json()
            
        logger.info(
            "SMR service returned serviceId",
            extra={
                "service_id": smr_response.get("serviceId"),
                "tenant_id": smr_response.get("tenant_id"),
                "is_free_user": smr_response.get("is_free_user"),
                "tenant_policy": smr_response.get("tenant_policy"),
                "service_policy": smr_response.get("service_policy"),
                "scoring_details": smr_response.get("scoring_details"),
                "headers_used": bool(latency_policy or cost_policy or accuracy_policy),
            }
        )
        
        # Log policy decision flow for debugging
        if latency_policy or cost_policy or accuracy_policy:
            logger.info(
                "SMR used header policies (highest priority, Policy Engine was skipped)",
                extra={
                    "latency_policy": latency_policy,
                    "cost_policy": cost_policy,
                    "accuracy_policy": accuracy_policy,
                    "tenant_id": tenant_id,
                }
            )
        elif tenant_id:
            logger.info(
                "SMR called Policy Engine for tenant policies",
                extra={
                    "tenant_id": tenant_id,
                    "tenant_policy_returned": smr_response.get("tenant_policy") is not None,
                }
            )
        else:
            logger.info(
                "SMR called Policy Engine for free-user policies",
                extra={
                    "tenant_policy_returned": smr_response.get("tenant_policy") is not None,
                }
            )
        
        return smr_response
        
    except httpx.HTTPStatusError as e:
        logger.error(
            "SMR service returned error status",
            extra={"status_code": e.response.status_code, "response": e.response.text},
            exc_info=True
        )
        # Try to extract error detail from SMR response
        error_detail = None
        smr_response_in_error = None
        try:
            error_response = e.response.json()
            error_detail = error_response.get("detail", {})
            # Try to extract SMR response if available in error response
            if "smr_response" in error_response:
                smr_response_in_error = error_response.get("smr_response")
            elif isinstance(error_detail, dict) and "smr_response" in error_detail:
                smr_response_in_error = error_detail.get("smr_response")
        except (ValueError, KeyError):
            # If response is not JSON or doesn't have expected structure, use generic error
            pass
        
        # Check if context-aware was requested
        context_aware_header = headers.get("X-Context-Aware") or headers.get("x-context-aware")
        is_context_aware = bool(
            context_aware_header
            and context_aware_header.strip().lower() in {"1", "true", "yes", "y"}
        )
        
        # If context-aware was requested, include SMR response in error and don't proceed with normal inference
        if is_context_aware:
            error_detail_dict = error_detail if isinstance(error_detail, dict) else {}
            # Ensure error_detail_dict is a dict
            if not isinstance(error_detail_dict, dict):
                error_detail_dict = {
                    "code": "SMR_SERVICE_ERROR",
                    "message": f"SMR service returned error: {e.response.text}",
                }
            # Include SMR response if available
            if smr_response_in_error:
                error_detail_dict["smr_response"] = smr_response_in_error
            raise HTTPException(
                status_code=e.response.status_code,
                detail=error_detail_dict,
            ) from e
        
        # For non-context-aware requests, handle normally
        if error_detail and isinstance(error_detail, dict) and error_detail.get("code") == "INVALID_POLICY_COMBINATION":
            raise HTTPException(
                status_code=e.response.status_code,
                detail=error_detail,
            ) from e
        
        raise HTTPException(
            status_code=e.response.status_code,
            detail={
                "code": "SMR_SERVICE_ERROR",
                "message": f"SMR service returned error: {e.response.text}",
            },
        ) from e
    except httpx.RequestError as e:
        logger.error("SMR service request failed", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SMR_SERVICE_UNAVAILABLE",
                "message": "SMR service is temporarily unavailable. Please try again.",
            },
        ) from e
    except Exception as e:
        logger.error("Unexpected error calling SMR service", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SMR_SERVICE_INTERNAL_ERROR",
                "message": f"Failed to call SMR service: {str(e)}",
            },
        ) from e


async def get_nmt_service(request: Request, db: AsyncSession = Depends(get_tenant_db_session)) -> NMTService:
    """
    Dependency to get configured NMT service.
    
    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    
    If context-aware is enabled, returns a minimal service that won't be used
    (context-aware requests use LLM translate API directly, not Triton).
    """
    # Check if context-aware is enabled - if so, we don't need to initialize NMTService properly
    # (context-aware requests use LLM translate API directly, not Triton)
    is_context_aware = getattr(request.state, "is_context_aware", False)
    if is_context_aware:
        # Return a minimal service - it won't be used since context-aware result is returned directly
        # But we need to return something to satisfy the dependency
        logger.info("Context-aware request detected, skipping NMTService Triton initialization")
        repository = NMTRepository(db)
        # Create a minimal service - it won't be used for context-aware requests
        return NMTService(repository, None)  # Pass None for triton_client since it won't be used
    
    repository = NMTRepository(db)
    text_service = TextService()
    
    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.state, "triton_api_key", None)
    
    logger.info(
        "get_nmt_service dependency called",
        extra={
            "has_triton_endpoint": bool(triton_endpoint),
            "triton_endpoint": triton_endpoint,
            "service_id": getattr(request.state, "service_id", None),
            "model_management_error": getattr(request.state, "model_management_error", None),
        }
    )
    
    if not triton_endpoint:
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        smr_response_data = getattr(request.state, "smr_response_data", None)
        
        if service_id:
            error_msg = (
                f"Model Management did not resolve serviceId: {service_id} and no default endpoint is allowed. "
                f"Please ensure the service is registered in Model Management database."
            )
            if model_mgmt_error:
                error_msg += f" Error: {model_mgmt_error}"
            
            error_detail = {
                "code": "ENDPOINT_RESOLUTION_FAILED",
                "message": error_msg,
            }
            # Include SMR response if SMR was called
            if smr_response_data:
                error_detail["smr_response"] = smr_response_data
            else:
                error_detail["smr_response"] = None
            
            logger.error(
                "Triton endpoint not resolved",
                extra={
                    "service_id": service_id,
                    "model_management_error": model_mgmt_error,
                    "smr_used": smr_response_data is not None,
                }
            )
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
        smr_response_data = getattr(request.state, "smr_response_data", None)
        
        error_detail = {
            "code": "MODEL_NAME_RESOLUTION_FAILED",
            "message": (
                f"Model Management did not resolve model name for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            ),
        }
        # Include SMR response if SMR was called
        if smr_response_data:
            error_detail["smr_response"] = smr_response_data
        else:
            error_detail["smr_response"] = None
        
        raise HTTPException(
            status_code=500,
            detail=error_detail,
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
    smr_response: Optional[Dict[str, Any]] = Depends(resolve_service_id_if_needed),
    nmt_service: NMTService = Depends(get_nmt_service)
) -> NMTInferenceResponse:
    """
    Run NMT inference on the given request.
    
    If SMR returned a context-aware result, it will be used directly.
    If context-aware was requested but SMR returned an error, the error is returned
    with SMR response included, and normal inference is skipped.
    Otherwise, normal NMT inference flow is used.
    """
    # Check if context-aware was requested
    context_aware_header = http_request.headers.get("X-Context-Aware") or http_request.headers.get("x-context-aware")
    is_context_aware = bool(
        context_aware_header
        and context_aware_header.strip().lower() in {"1", "true", "yes", "y"}
    )
    
    # If context-aware was requested, we should either have a context_aware_result or an error
    # If context-aware was requested but no context_aware_result and no serviceId was provided,
    # it means SMR should have been called but didn't return a result - this shouldn't happen
    # but if it does, we should not proceed with normal inference
    if is_context_aware:
        # If context-aware was requested, we should have either:
        # 1. context_aware_result (success)
        # 2. An error (which would have been raised in dependency)
        # If we get here without context_aware_result and serviceId was not provided,
        # something went wrong - don't proceed with normal inference
        if not request.config.serviceId and (not smr_response or not smr_response.get("context_aware_result")):
            logger.error(
                "Context-aware was requested but no result or error was returned",
                extra={
                    "context": {
                        "has_smr_response": bool(smr_response),
                        "has_context_aware_result": bool(smr_response and smr_response.get("context_aware_result")),
                        "has_service_id": bool(request.config.serviceId),
                    }
                }
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "CONTEXT_AWARE_ERROR",
                    "message": "Context-aware routing was requested but failed to return a result. Please check SMR service logs.",
                    "smr_response": smr_response if smr_response else None,
                },
            )
    
    # Check if SMR returned a context-aware result
    if smr_response and smr_response.get("context_aware_result"):
        logger.info(
            "NMT inference: Using context-aware result from SMR",
            extra={
                "context": {
                    "user_id": getattr(http_request.state, "user_id", None),
                    "tenant_id": getattr(http_request.state, "tenant_id", None),
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
        return response
    
    # Normal SMR flow when context-aware is not enabled or serviceId was already provided
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
            tenant_id = getattr(http_request.state, "tenant_id", None)
            
            # Get correlation ID for log/trace correlation
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)

            # Get SMR response data from dependency (if SMR was called)
            smr_response_data = smr_response or getattr(http_request.state, "smr_response_data", None)
            if smr_response_data:
                span.add_event("nmt.smr.called", {"reason": "serviceId_missing"})
                span.add_event("nmt.smr.completed", {"service_id": request.config.serviceId})
                span.set_attribute("nmt.smr_used", True)
            else:
                span.set_attribute("nmt.smr_used", False)

            # Calculate input metrics (character length and word count)
            input_texts = [text_input.source for text_input in request.input]
            total_input_characters = sum(len(text) for text in input_texts)
            total_input_words = sum(count_words(text) for text in input_texts)
            
            # Store input details in request.state for middleware to access
            http_request.state.input_details = {
                "character_length": total_input_characters,
                "word_count": total_input_words,
                "input_count": len(request.input)
            }
            
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
                auth_headers=extract_auth_headers(http_request),
                http_request=http_request,
            )
            
            # Calculate output metrics (character length and word count) for successful responses
            output_texts = [output.target for output in response.output]
            total_output_characters = sum(len(text) for text in output_texts)
            total_output_words = sum(count_words(text) for text in output_texts)
            
            # Store output details in request.state for middleware to access
            http_request.state.output_details = {
                "character_length": total_output_characters,
                "word_count": total_output_words,
                "output_count": len(response.output)
            }
            
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
            
            # Include SMR response in the final response (null if SMR was not called)
            response_dict = response.dict()
            if smr_response_data:
                response_dict["smr_response"] = smr_response_data
                logger.info(
                    "Including SMR response in NMT inference response",
                    extra={"smr_service_id": smr_response_data.get("serviceId")}
                )
            else:
                response_dict["smr_response"] = None
            # Create new response object with SMR data
            response = NMTInferenceResponse(**response_dict)
            
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
                    "smr_used": smr_response_data is not None,
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
            # Get SMR response if available
            smr_response_data = getattr(http_request.state, "smr_response_data", None)
            
            if "Triton" in str(exc) or "triton" in str(exc).lower():
                error_code = MODEL_UNAVAILABLE if model_name else SERVICE_UNAVAILABLE
                error_message = MODEL_UNAVAILABLE_NMT_MESSAGE if model_name else SERVICE_UNAVAILABLE_NMT_MESSAGE
                error_detail = ErrorDetail(code=error_code, message=error_message).dict()
                # Include SMR response if SMR was called
                if smr_response_data:
                    error_detail["smr_response"] = smr_response_data
                else:
                    error_detail["smr_response"] = None
                raise HTTPException(
                    status_code=503,
                    detail=error_detail
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
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)
    
    # Get SMR response data from request state (if SMR was called in dependency)
    smr_response_data = getattr(http_request.state, "smr_response_data", None)
    
    # Validate request
    validate_service_id(request.config.serviceId)
    validate_language_pair(
        request.config.language.sourceLanguage,
        request.config.language.targetLanguage
    )
    validate_batch_size(len(request.input))

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
        auth_headers=extract_auth_headers(http_request),
        http_request=http_request,
    )
    
    # Include SMR response in the final response (null if SMR was not called)
    response_dict = response.dict()
    if smr_response_data:
        response_dict["smr_response"] = smr_response_data
        logger.info(
            "Including SMR response in NMT inference response (fallback mode)",
            extra={"smr_service_id": smr_response_data.get("serviceId")}
        )
    else:
        response_dict["smr_response"] = None
    response = NMTInferenceResponse(**response_dict)
    
    logger.info("NMT inference completed successfully")
    return response
 
