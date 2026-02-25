"""
Inference Router
FastAPI router for NMT inference endpoints
"""

import logging
import os
import time
from typing import Dict, Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
from middleware.tenant_context import try_get_tenant_context
import os
import httpx

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
    INTERNAL_SERVER_ERROR_MESSAGE,
    SERVICE_UNPUBLISHED,
    SERVICE_UNPUBLISHED_MESSAGE,
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
    # Log removed - middleware handles request/response logging
    
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
        
        # Extract fallback service ID from SMR response
        fallback_service_id = smr_response_data.get("fallbackServiceId")
        if fallback_service_id:
            logger.info(
                "NMT: Fallback service ID available from SMR",
                extra={
                    "primary_service_id": service_id,
                    "fallback_service_id": fallback_service_id,
                }
            )
            # Store fallback service ID in request state for potential retry
            http_request.state.fallback_service_id = fallback_service_id
        
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
                elif service_info.is_published is not True:
                    logger.warning(
                        "NMT inference rejected: service is unpublished",
                        extra={"service_id": service_id},
                    )
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": SERVICE_UNPUBLISHED,
                            "message": SERVICE_UNPUBLISHED_MESSAGE,
                            "serviceId": service_id,
                        },
                    )
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
        
        # Log all X-* headers to debug
        x_headers = {k: v for k, v in headers.items() if k.startswith("X-") or k.startswith("x-")}
        logger.info(
            "NMT: Extracting headers for SMR call",
            extra={
                "x_headers": x_headers,
                "all_header_keys": list(headers.keys()),
            }
        )
        
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
        
        # Forward request profiler header to SMR
        request_profiler_header = headers.get("X-Request-Profiler") or headers.get("x-request-profiler")
        if request_profiler_header:
            smr_headers["X-Request-Profiler"] = request_profiler_header
            logger.info(
                "NMT: Forwarding X-Request-Profiler header to SMR",
                extra={
                    "request_profiler_header": request_profiler_header,
                    "smr_headers_keys": list(smr_headers.keys()),
                }
            )
        else:
            logger.info(
                "NMT: No X-Request-Profiler header found to forward",
                extra={
                    "all_headers_keys": list(headers.keys()),
                    "profiler_headers": {k: v for k, v in headers.items() if "profiler" in k.lower()},
                }
            )
        
        logger.info(
            "Calling SMR service to get serviceId",
            extra={
                "user_id": user_id,
                "tenant_id": tenant_id,
                "has_policy_headers": bool(latency_policy or cost_policy or accuracy_policy),
                "has_request_profiler": bool(request_profiler_header),
                "smr_headers": {k: v for k, v in smr_headers.items() if k.startswith("X-")},
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


async def switch_to_fallback_service(
    request: NMTInferenceRequest,
    http_request: Request,
    fallback_service_id: str,
) -> None:
    """
    Switch to fallback service by resolving its endpoint and updating request state.
    
    Args:
        request: NMT inference request
        http_request: FastAPI request object
        fallback_service_id: Fallback service ID from SMR
    """
    logger.info(
        "NMT: Switching to fallback service",
        extra={
            "primary_service_id": request.config.serviceId,
            "fallback_service_id": fallback_service_id,
        }
    )
    
    # Update request with fallback service ID
    request.config.serviceId = fallback_service_id
    http_request.state.service_id = fallback_service_id
    
    # Resolve Triton endpoint for fallback service
    model_management_client = getattr(http_request.app.state, "model_management_client", None)
    redis_client = getattr(http_request.app.state, "redis_client", None)
    
    if not model_management_client:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "MODEL_MANAGEMENT_UNAVAILABLE",
                "message": "Model Management client not available for fallback service resolution",
            },
        )
    
    try:
        auth_headers = extract_auth_headers(http_request)
        service_info = await model_management_client.get_service(
            service_id=fallback_service_id,
            use_cache=True,
            redis_client=redis_client,
            auth_headers=auth_headers,
        )
        
        if not service_info or not service_info.endpoint:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "FALLBACK_SERVICE_UNAVAILABLE",
                    "message": f"Fallback service {fallback_service_id} not found or has no endpoint configured",
                },
            )
        if service_info.is_published is not True:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": SERVICE_UNPUBLISHED,
                    "message": SERVICE_UNPUBLISHED_MESSAGE,
                    "serviceId": fallback_service_id,
                },
            )
        
        triton_endpoint = service_info.endpoint
        triton_api_key = service_info.api_key or ""
        
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
        
        # Update request state with fallback service endpoint
        http_request.state.triton_endpoint = triton_endpoint
        http_request.state.triton_api_key = triton_api_key
        http_request.state.triton_model_name = triton_model_name
        http_request.state.using_fallback_service = True
        
        logger.info(
            "NMT: Successfully switched to fallback service",
            extra={
                "fallback_service_id": fallback_service_id,
                "triton_endpoint": triton_endpoint,
                "triton_model_name": triton_model_name,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "NMT: Failed to resolve fallback service endpoint",
            extra={"fallback_service_id": fallback_service_id, "error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "FALLBACK_SERVICE_RESOLUTION_FAILED",
                "message": f"Failed to resolve endpoint for fallback service {fallback_service_id}: {str(e)}",
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
    
    # Log removed - middleware handles request/response logging
    
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
    
    # Log removed - middleware handles request/response logging
    
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


API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")


async def _enforce_tenant_and_service_checks(http_request: Request, service_name: str = "nmt"):
    """
    Enforce tenant subscription, tenant status (ACTIVE) and global service active flag.
    Execution order:
      1) If tenant context exists, ensure tenant subscribes to this service
      2) Ensure the service is globally active via /list/services
      3) If tenant context exists, ensure tenant.status == ACTIVE.
    """
    # Skip tenant and service availability checks for anonymous Try-It requests.
    # API Gateway forwards X-Try-It: true for /api/v1/try-it calls which proxy to NMT.
    try_it_header = http_request.headers.get("X-Try-It") or http_request.headers.get("x-try-it")
    if try_it_header and str(try_it_header).strip().lower() == "true":
        return

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

    if tenant_id:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/admin/view/tenant", params={"tenant_id": tenant_id}, headers=headers)
                if resp.status_code == 200:
                    tenant_data = resp.json()
                    subscriptions = [str(s).lower() for s in (tenant_data.get("subscriptions") or [])]
                    if service_name.lower() not in subscriptions:
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
    if headers.get("Authorization") or headers.get("authorization"):
        service_check_headers["Authorization"] = headers.get("Authorization") or headers.get("authorization")
    # Don't forward X-API-Key or X-Auth-Source for multi-tenant endpoints
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            svc_resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/list/services", headers=service_check_headers)
            if svc_resp.status_code == 200:
                services = svc_resp.json().get("services", [])
                svc_entry = next((s for s in services if str(s.get("service_name")).lower() == service_name.lower()), None)
                if not svc_entry or not svc_entry.get("is_active", False):
                    raise HTTPException(status_code=503, detail=ErrorDetail(code=SERVICE_UNAVAILABLE, message="NMT service is not active at the moment.Please contact your administrator").dict())
            else:
                raise HTTPException(status_code=503, detail=ErrorDetail(code=SERVICE_UNAVAILABLE, message="Cannot detect service availability. Please contact your administrator").dict())
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail=ErrorDetail(code=SERVICE_UNAVAILABLE, message=SERVICE_UNAVAILABLE_NMT_MESSAGE).dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to verify service active state for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=ErrorDetail(code=SERVICE_UNAVAILABLE, message=SERVICE_UNAVAILABLE_NMT_MESSAGE).dict())

    # Finally, if tenant context present, enforce tenant status (must be ACTIVE)
    if tenant_id:
        try:
            # reuse tenant_data if loaded above
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

async def enforce_nmt_checks(request: Request):
    """FastAPI dependency that enforces tenant and service checks for NMT before other dependencies run."""
    # the service name is coming from multitenant SubscriptionType enum
    await _enforce_tenant_and_service_checks(request, service_name="nmt")

# Add as a router-level dependency so it runs after router-level auth dependency
# Ensure AuthProvider (declared in APIRouter(..., dependencies=[Depends(AuthProvider)]))
# runs first by appending enforce_nmt_checks instead of inserting at position 0.
inference_router.dependencies.append(Depends(enforce_nmt_checks))


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

            # Log removed - middleware handles request/response logging

            # Run inference with fallback support
            fallback_service_id = getattr(http_request.state, "fallback_service_id", None)
            using_fallback = False
            
            try:
                # Try primary service first
                response = await nmt_service.run_inference(
                    request=request,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id,
                    auth_headers=extract_auth_headers(http_request),
                    http_request=http_request,
                )
            except (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError) as primary_error:
                # Store original service ID before attempting fallback
                original_service_id = request.config.serviceId
                
                # Primary service failed - try fallback if available and different from primary
                if fallback_service_id and fallback_service_id != original_service_id:
                    logger.warning(
                        "NMT: Primary service failed, attempting fallback",
                        extra={
                            "primary_service_id": request.config.serviceId,
                            "fallback_service_id": fallback_service_id,
                            "error_type": type(primary_error).__name__,
                            "error_message": str(primary_error),
                        },
                        exc_info=True
                    )
                    
                    span.add_event("nmt.fallback.triggered", {
                        "primary_service_id": request.config.serviceId,
                        "fallback_service_id": fallback_service_id,
                        "error_type": type(primary_error).__name__,
                    })
                    
                    try:
                        # Switch to fallback service
                        await switch_to_fallback_service(
                            request=request,
                            http_request=http_request,
                            fallback_service_id=fallback_service_id,
                        )
                        
                        # Get new NMT service instance with fallback endpoint
                        # Create service components for fallback - reuse same components as primary
                        # but with updated endpoint from request state
                        triton_endpoint = getattr(http_request.state, "triton_endpoint")
                        triton_api_key = getattr(http_request.state, "triton_api_key", "")
                        triton_model_name = getattr(http_request.state, "triton_model_name", "unknown")
                        
                        # Create a factory function for the fallback endpoint (same pattern as primary)
                        def get_fallback_triton_client_for_endpoint(endpoint: str) -> TritonClient:
                            """Create Triton client for fallback endpoint"""
                            from utils.triton_client import TritonClient
                            triton_url = endpoint
                            if triton_url.startswith(('http://', 'https://')):
                                triton_url = triton_url.split('://', 1)[1]
                            return TritonClient(triton_url=triton_url, api_key=triton_api_key)
                        
                        # Get Model Management client and Redis client from app state (same as primary)
                        model_management_client = getattr(http_request.app.state, "model_management_client", None)
                        redis_client = getattr(http_request.app.state, "redis_client", None)
                        
                        # Verify Model Management client is available
                        if not model_management_client:
                            logger.error(
                                "NMT: Model Management client not available in app.state for fallback service",
                                extra={
                                    "fallback_service_id": fallback_service_id,
                                    "app_state_keys": list(http_request.app.state.__dict__.keys()) if hasattr(http_request.app.state, "__dict__") else None,
                                }
                            )
                            raise HTTPException(
                                status_code=500,
                                detail={
                                    "code": "MODEL_MANAGEMENT_UNAVAILABLE",
                                    "message": "Model Management client not available for fallback service. This is required for service resolution.",
                                },
                            )
                        
                        logger.info(
                            "NMT: Model Management client available for fallback service",
                            extra={
                                "fallback_service_id": fallback_service_id,
                                "has_redis_client": bool(redis_client),
                            }
                        )
                        
                        # Get database session for fallback service
                        from repositories.nmt_repository import NMTRepository
                        from services.text_service import TextService
                        from middleware.tenant_db_dependency import get_tenant_db_session
                        
                        fallback_db = await get_tenant_db_session(http_request)
                        fallback_repository = NMTRepository(fallback_db)
                        fallback_text_service = TextService()
                        
                        # Get cache TTL from Model Management client config
                        cache_ttl_seconds = getattr(model_management_client, "cache_ttl_seconds", 300)
                        
                        # Create fallback NMT service with Model Management client (required for dynamic endpoint resolution)
                        fallback_nmt_service = NMTService(
                            repository=fallback_repository,
                            text_service=fallback_text_service,
                            get_triton_client_func=get_fallback_triton_client_for_endpoint,
                            model_management_client=model_management_client,
                            redis_client=redis_client,
                            cache_ttl_seconds=cache_ttl_seconds
                        )
                        
                        # Pre-populate the fallback service cache with the already-resolved endpoint
                        # This avoids another Model Management call when get_triton_client is invoked
                        # The cache will be used by get_triton_client, and the verification step will
                        # also use the cached service registry entry, avoiding Model Management calls
                        import time
                        expires_at = time.time() + cache_ttl_seconds
                        fallback_triton_client = get_fallback_triton_client_for_endpoint(triton_endpoint)
                        
                        # Pre-populate Triton client cache
                        fallback_nmt_service._triton_clients[fallback_service_id] = (
                            fallback_triton_client,
                            triton_endpoint,
                            expires_at
                        )
                        
                        # Pre-populate service registry cache (used by _get_service_registry_entry)
                        # This is critical - it prevents Model Management calls during endpoint verification
                        fallback_nmt_service._service_registry_cache[fallback_service_id] = (
                            triton_endpoint,
                            triton_model_name,
                            expires_at
                        )
                        
                        # Also pre-populate service info cache (used by _get_service_info)
                        # This provides an additional layer of protection
                        from utils.model_management_client import ServiceInfo
                        fallback_service_info = ServiceInfo(
                            service_id=fallback_service_id,
                            model_id="",  # Not needed for fallback
                            endpoint=triton_endpoint,
                            api_key=triton_api_key,
                            triton_model=triton_model_name,
                            model_name=triton_model_name,
                        )
                        fallback_nmt_service._service_info_cache[fallback_service_id] = (
                            fallback_service_info,
                            expires_at
                        )
                        
                        logger.info(
                            "NMT: Pre-populated fallback service cache",
                            extra={
                                "fallback_service_id": fallback_service_id,
                                "triton_endpoint": triton_endpoint,
                                "triton_model_name": triton_model_name,
                            }
                        )
                        
                        # Retry inference with fallback service
                        logger.info(
                            "NMT: Retrying inference with fallback service",
                            extra={"fallback_service_id": fallback_service_id}
                        )
                        
                        response = await fallback_nmt_service.run_inference(
                            request=request,
                            user_id=user_id,
                            api_key_id=api_key_id,
                            session_id=session_id,
                            auth_headers=extract_auth_headers(http_request),
                            http_request=http_request,
                        )
                        
                        using_fallback = True
                        span.add_event("nmt.fallback.success", {
                            "fallback_service_id": fallback_service_id,
                        })
                        span.set_attribute("nmt.fallback_used", True)
                        span.set_attribute("nmt.fallback_service_id", fallback_service_id)
                        
                        logger.info(
                            "NMT: Fallback service succeeded",
                            extra={"fallback_service_id": fallback_service_id}
                        )
                        
                    except Exception as fallback_error:
                        # Fallback also failed - create detailed error message
                        # Use the original_service_id from the outer scope
                        primary_service_id = original_service_id
                        
                        # Extract error details from both errors
                        primary_error_msg = str(primary_error)
                        fallback_error_msg = str(fallback_error)
                        
                        # Determine error types
                        primary_error_type = type(primary_error).__name__
                        fallback_error_type = type(fallback_error).__name__
                        
                        logger.error(
                            "NMT: Both primary and fallback services failed",
                            extra={
                                "primary_service_id": primary_service_id,
                                "fallback_service_id": fallback_service_id,
                                "primary_error_type": primary_error_type,
                                "primary_error": primary_error_msg,
                                "fallback_error_type": fallback_error_type,
                                "fallback_error": fallback_error_msg,
                            },
                            exc_info=True
                        )
                        
                        span.add_event("nmt.fallback.failed", {
                            "primary_service_id": primary_service_id,
                            "fallback_service_id": fallback_service_id,
                            "primary_error_type": primary_error_type,
                            "fallback_error_type": fallback_error_type,
                        })
                        
                        # Create a comprehensive error message with both service failures
                        combined_error_message = (
                            f"Primary service ({primary_service_id}) failed: {primary_error_msg}. "
                            f"Fallback service ({fallback_service_id}) also failed: {fallback_error_msg}"
                        )
                        
                        # Store error details in request state for error handler to access
                        http_request.state.fallback_failure_details = {
                            "primary_service_id": primary_service_id,
                            "fallback_service_id": fallback_service_id,
                            "primary_error": {
                                "type": primary_error_type,
                                "message": primary_error_msg,
                            },
                            "fallback_error": {
                                "type": fallback_error_type,
                                "message": fallback_error_msg,
                            },
                        }
                        
                        # Re-raise with combined error message
                        raise TritonInferenceError(combined_error_message) from fallback_error
                else:
                    # No fallback available - re-raise original error
                    raise
            
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
                # Update SMR response if fallback was used
                if using_fallback:
                    smr_response_data = smr_response_data.copy()
                    smr_response_data["fallback_used"] = True
                    original_service_id = smr_response_data.get("serviceId")
                    smr_response_data["original_service_id"] = original_service_id
                    smr_response_data["serviceId"] = fallback_service_id
                    smr_response_data["fallback_message"] = (
                        f"The service ID selected by SMR was '{original_service_id}' but it didn't work. "
                        f"Fallback service ID '{fallback_service_id}' is used instead."
                    )
                    logger.info(
                        "Including SMR response with fallback usage",
                        extra={
                            "original_service_id": original_service_id,
                            "fallback_service_id": fallback_service_id,
                            "fallback_message": smr_response_data["fallback_message"],
                        }
                    )
                else:
                    logger.info(
                        "Including SMR response in NMT inference response",
                        extra={"smr_service_id": smr_response_data.get("serviceId")}
                    )
                response_dict["smr_response"] = smr_response_data
            else:
                response_dict["smr_response"] = None
            # Create new response object with SMR data
            response = NMTInferenceResponse(**response_dict)
            
            # Log removed - middleware handles request/response logging
            
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
            
            # Check if both primary and fallback services failed
            fallback_failure_details = getattr(http_request.state, "fallback_failure_details", None)
            
            # Return appropriate error based on exception type
            # Get SMR response if available
            smr_response_data = getattr(http_request.state, "smr_response_data", None)
            
            if "Triton" in str(exc) or "triton" in str(exc).lower():
                error_code = MODEL_UNAVAILABLE if model_name else SERVICE_UNAVAILABLE
                
                # If both services failed, provide detailed error message
                if fallback_failure_details:
                    error_message = (
                        f"Primary service ({fallback_failure_details['primary_service_id']}) failed: "
                        f"{fallback_failure_details['primary_error']['message']}. "
                        f"Fallback service ({fallback_failure_details['fallback_service_id']}) also failed: "
                        f"{fallback_failure_details['fallback_error']['message']}"
                    )
                else:
                    error_message = MODEL_UNAVAILABLE_NMT_MESSAGE if model_name else SERVICE_UNAVAILABLE_NMT_MESSAGE
                
                error_detail = ErrorDetail(code=error_code, message=error_message).dict()
                
                # Include detailed failure information if both services failed
                if fallback_failure_details:
                    error_detail["primary_service_id"] = fallback_failure_details["primary_service_id"]
                    error_detail["fallback_service_id"] = fallback_failure_details["fallback_service_id"]
                    error_detail["primary_error"] = fallback_failure_details["primary_error"]
                    error_detail["fallback_error"] = fallback_failure_details["fallback_error"]
                
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
    
    # tenant/service checks are enforced via router-level dependency
    
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    # Log removed - middleware handles request/response logging

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
    
    # Log removed - middleware handles request/response logging
    return response
 
