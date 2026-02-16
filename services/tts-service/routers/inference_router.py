"""
FastAPI router for TTS inference endpoints.
"""

import logging
import time
import traceback
import os
from typing import Dict, Any, Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.tts_request import TTSInferenceRequest
from models.tts_response import TTSInferenceResponse
from repositories.tts_repository import TTSRepository
from services.tts_service import TTSService
from services.audio_service import AudioService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.validation_utils import (
    validate_language_code,
    validate_service_id,
    validate_gender,
    validate_audio_format,
    validate_sample_rate,
    validate_text_input,
    validate_audio_duration,
    InvalidLanguageCodeError,
    InvalidServiceIdError,
    InvalidGenderError,
    InvalidAudioFormatError,
    InvalidSampleRateError,
    NoTextInputError,
    TextTooShortError,
    TextTooLongError,
    InvalidCharactersError,
    EmptyInputError,
    LanguageMismatchError,
    VoiceNotAvailableError
)
from middleware.exceptions import AuthenticationError, AuthorizationError, ErrorDetail
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
    LANGUAGE_MISMATCH,
    LANGUAGE_MISMATCH_MESSAGE,
    LANGUAGE_NOT_SUPPORTED,
    LANGUAGE_NOT_SUPPORTED_TTS_MESSAGE,
    VOICE_NOT_AVAILABLE,
    VOICE_NOT_AVAILABLE_MESSAGE,
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_TTS_MESSAGE,
    PROCESSING_FAILED,
    PROCESSING_FAILED_MESSAGE,
    MODEL_UNAVAILABLE,
    MODEL_UNAVAILABLE_TTS_MESSAGE,
    AUDIO_GEN_FAILED,
    AUDIO_GEN_FAILED_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_TTS_MESSAGE,
    INTERNAL_SERVER_ERROR,
    INTERNAL_SERVER_ERROR_MESSAGE
)
from middleware.exceptions import AuthenticationError, AuthorizationError
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id

logger = logging.getLogger(__name__)

# SMR Service Configuration
SMR_SERVICE_URL = os.getenv("SMR_SERVICE_URL", "http://smr-service:8097")


def count_words(text: str) -> int:
    """Count words in text"""
    try:
        words = [word for word in text.split() if word.strip()]
        return len(words)
    except Exception:
        return 0
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("tts-service")

# Create router
# Enforce auth and permission checks on all routes (same as OCR and NMT)
inference_router = APIRouter(
    prefix="/api/v1/tts", 
    tags=["TTS Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def resolve_service_id_if_needed(
    request: TTSInferenceRequest,
    http_request: Request,
) -> Optional[Dict[str, Any]]:
    """
    Dependency to resolve serviceId via SMR if not provided in request.
    
    Flow:
    1. Check if serviceId is in request body
       - YES → Use it directly (skip SMR), return None
       - NO  → Extract tenant_id from JWT token
               - Found → Pass tenant_id to SMR
               - Not found → Pass "" (empty string) to SMR
               → SMR determines free/non-free and returns serviceId
    
    Returns SMR response data if SMR was called, None otherwise.
    """
    try:
        print("DEBUG: TTS resolve_service_id_if_needed dependency called", flush=True)
        logger.info(
            "TTS resolve_service_id_if_needed dependency called",
            extra={
                "has_service_id": bool(request and request.config and request.config.serviceId),
                "service_id": request.config.serviceId if (request and request.config) else None,
                "request_type": type(request).__name__ if request else "None",
            },
        )
    except Exception as e:
        print(f"DEBUG: TTS resolve_service_id_if_needed ERROR in logging: {e}", flush=True)
        logger.error(f"TTS resolve_service_id_if_needed: Error in initial logging: {e}", exc_info=True)

    # Check: Is serviceId in request body?
    if request.config.serviceId:
        # YES → Use it directly (skip SMR)
        logger.info(
            "TTS serviceId provided in request, skipping SMR",
            extra={"service_id": request.config.serviceId}
        )
        # Set in request.state for Model Management middleware and ensure_service_id_resolved
        http_request.state.service_id = request.config.serviceId
        return None  # SMR was not called
    
    # NO → Extract tenant_id from JWT token only
    # (This code only runs if serviceId is NOT in request body)
    user_id = getattr(http_request.state, "user_id", None)

    # Extract tenant_id ONLY from auth token (JWT payload).
    # - If tenant_id is present in JWT -> pass that to SMR (non-free user).
    # - If tenant_id is NOT present in JWT -> pass empty string "" to SMR (free user).
    jwt_payload = getattr(http_request.state, "jwt_payload", None)
    tenant_id_from_jwt = jwt_payload.get("tenant_id") if jwt_payload else None
    tenant_id_for_smr = tenant_id_from_jwt or ""

    logger.info(
        "TTS serviceId not provided, calling SMR service (dependency)",
        extra={
            "user_id": user_id,
            "tenant_id_from_jwt": tenant_id_from_jwt,
            "tenant_id_passed_to_smr": tenant_id_for_smr,
        },
    )

    # Prepare request body for SMR (preserve all fields)
    try:
        # Pydantic v2
        request_body = request.model_dump(exclude_none=False)
    except AttributeError:
        # Pydantic v1
        request_body = request.dict(exclude_none=False)

    smr_response_data = await call_smr_service(
        request_body=request_body,
        user_id=str(user_id) if user_id else None,
        tenant_id=tenant_id_for_smr,
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
            extra={"service_id": service_id},
        )
        http_request.state.model_management_error = "Model Management client not available in application state"
    else:
        try:
            # Extract auth headers from request (case-insensitive)
            auth_headers: Dict[str, str] = {}
            
            # Check Authorization header (case-insensitive)
            authorization = http_request.headers.get("Authorization") or http_request.headers.get("authorization")
            if authorization:
                auth_headers["Authorization"] = authorization
            
            # Check X-API-Key header (case-insensitive)
            x_api_key = http_request.headers.get("X-API-Key") or http_request.headers.get("x-api-key")
            if x_api_key:
                auth_headers["X-API-Key"] = x_api_key
            
            # Check X-Auth-Source header (important for JWT vs API key authentication)
            x_auth_source = http_request.headers.get("X-Auth-Source") or http_request.headers.get("x-auth-source")
            if x_auth_source:
                auth_headers["X-Auth-Source"] = x_auth_source

            logger.debug(
                "TTS: Extracted auth headers for model-management call",
                extra={
                    "has_authorization": "Authorization" in auth_headers,
                    "has_api_key": "X-API-Key" in auth_headers,
                    "has_auth_source": "X-Auth-Source" in auth_headers,
                    "service_id": service_id,
                },
            )

            service_info = await model_management_client.get_service(
                service_id=service_id,
                use_cache=True,
                redis_client=redis_client,
                auth_headers=auth_headers,
            )

            if not service_info:
                logger.error(
                    "TTS service not found in Model Management",
                    extra={"service_id": service_id},
                )
                http_request.state.model_management_error = (
                    f"Service {service_id} not found in Model Management database"
                )
            elif not service_info.endpoint:
                logger.error(
                    "TTS service found but has no endpoint configured",
                    extra={
                        "service_id": service_id,
                        "service_name": service_info.name,
                        "model_id": service_info.model_id,
                    },
                )
                http_request.state.model_management_error = (
                    f"Service {service_id} found but has no endpoint configured"
                )
            else:
                triton_endpoint = service_info.endpoint
                triton_api_key = service_info.api_key or ""

                # Extract model name from inference endpoint / model info
                # Use the same logic as Model Management middleware for consistency
                triton_model_name = None
                
                # Try to infer model name from model inference endpoint metadata (highest priority)
                if service_info.model_inference_endpoint:
                    inference_endpoint = service_info.model_inference_endpoint
                    if isinstance(inference_endpoint, dict):
                        # Check inside schema FIRST (most specific location for Triton model name)
                        schema = inference_endpoint.get("schema", {})
                        if isinstance(schema, dict):
                            triton_model_name = (
                                schema.get("model_name")
                                or schema.get("modelName")
                                or schema.get("name")
                            )
                        
                        # If not in schema, check top-level inference_endpoint
                        if not triton_model_name:
                            triton_model_name = (
                                inference_endpoint.get("model_name")
                                or inference_endpoint.get("modelName")
                                or inference_endpoint.get("model")
                            )
                
                # Fall back to triton_model from task.type (least specific)
                if not triton_model_name:
                    triton_model_name = service_info.triton_model
                
                # Fall back to model_name
                if not triton_model_name:
                    triton_model_name = service_info.model_name
                
                # If still no model name, try to extract from service_id
                if not triton_model_name and service_id:
                    parts = service_id.split("/")
                    if len(parts) > 1:
                        model_part = parts[-1]
                        if "--" in model_part:
                            triton_model_name = model_part.split("--")[0]
                        else:
                            triton_model_name = model_part
                
                # Final fallback
                if not triton_model_name:
                    triton_model_name = "unknown"
                    logger.warning(
                        f"Could not determine Triton model name for service {service_id}. "
                        f"Using 'unknown' - this may cause Triton inference to fail.",
                        extra={"service_id": service_id}
                    )

                http_request.state.triton_endpoint = triton_endpoint
                http_request.state.triton_model_name = triton_model_name
                # Store model_id from service_info for database record
                # Use model_id from service_info if available, otherwise fallback to service_id
                model_id_for_db = service_info.model_id or service_id
                http_request.state.model_id = model_id_for_db
                # Preserve API key in app.state like existing flow
                if not getattr(http_request.app.state, "triton_api_key", None):
                    http_request.app.state.triton_api_key = triton_api_key

                logger.info(
                    "TTS: Manually resolved Triton endpoint for SMR-selected serviceId",
                    extra={
                        "service_id": service_id,
                        "model_id": model_id_for_db,
                        "triton_endpoint": triton_endpoint,
                        "triton_model_name": triton_model_name,
                        "has_api_key": bool(triton_api_key),
                        "model_inference_endpoint": str(service_info.model_inference_endpoint) if service_info.model_inference_endpoint else None,
                        "service_info_triton_model": service_info.triton_model,
                        "service_info_model_name": service_info.model_name,
                    },
                )
        except Exception as e:
            logger.error(
                "TTS: Error resolving Triton endpoint for SMR-selected serviceId",
                extra={"service_id": service_id, "error": str(e)},
                exc_info=True,
            )
            http_request.state.model_management_error = str(e)
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
    
    logger.info(
        "TTS: Stored SMR response data in request state",
        extra={
            "has_smr_response": smr_response_data is not None,
            "smr_service_id": smr_response_data.get("serviceId") if smr_response_data else None,
            "smr_tenant_id": smr_response_data.get("tenant_id") if smr_response_data else None,
            "smr_is_free_user": smr_response_data.get("is_free_user") if smr_response_data else None,
            "smr_response_keys": list(smr_response_data.keys()) if smr_response_data and isinstance(smr_response_data, dict) else None,
        },
    )

    # Verify that endpoint was set (if Model Management client was available)
    if model_management_client:
        triton_endpoint_check = getattr(http_request.state, "triton_endpoint", None)
        if not triton_endpoint_check:
            model_mgmt_error = getattr(http_request.state, "model_management_error", None)
            error_msg = f"Failed to resolve Triton endpoint for serviceId: {service_id}"
            if model_mgmt_error:
                error_msg += f". {model_mgmt_error}"
            else:
                error_msg += (
                    ". Please ensure the service is registered in Model Management "
                    "database with a valid endpoint."
                )

            logger.error(
                "TTS: Failed to resolve Triton endpoint after SMR call",
                extra={
                    "service_id": service_id,
                    "model_management_error": model_mgmt_error,
                },
            )
            error_detail = {
                "code": "ENDPOINT_RESOLUTION_FAILED",
                "message": error_msg,
                "smr_response": smr_response_data,
            }
            raise HTTPException(
                status_code=500,
                detail=error_detail,
            )

        logger.info(
            "TTS SMR service returned serviceId, updated request (dependency)",
            extra={
                "service_id": request.config.serviceId,
                "user_id": getattr(http_request.state, "user_id", None),
                "tenant_id": getattr(http_request.state, "tenant_id", None),
                "endpoint_resolved": bool(getattr(http_request.state, "triton_endpoint", None)),
            },
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
    Call SMR service to get serviceId for the TTS request.

    Mirrors ASR/NMT SMR integration but with task_type='tts'.
    """
    try:
        headers = dict(http_request.headers)
        latency_policy = headers.get("X-Latency-Policy") or headers.get("x-latency-policy")
        cost_policy = headers.get("X-Cost-Policy") or headers.get("x-cost-policy")
        accuracy_policy = headers.get("X-Accuracy-Policy") or headers.get("x-accuracy-policy")

        smr_payload = {
            "task_type": "tts",
            "request_body": request_body,
            "user_id": str(user_id) if user_id else None,
            "tenant_id": str(tenant_id) if tenant_id else None,
        }

        smr_headers: Dict[str, str] = {}
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

        logger.info(
            "Calling SMR service to get TTS serviceId",
            extra={
                "user_id": user_id,
                "tenant_id": tenant_id,
                "has_policy_headers": bool(latency_policy or cost_policy or accuracy_policy),
            },
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{SMR_SERVICE_URL}/api/v1/smr/select-service",
                json=smr_payload,
                headers=smr_headers,
            )
            response.raise_for_status()
            smr_response = response.json()
            
            # Log full SMR response for debugging
            logger.info(
                "SMR service returned response (full)",
                extra={
                    "status_code": response.status_code,
                    "smr_response_keys": list(smr_response.keys()) if isinstance(smr_response, dict) else None,
                    "smr_response_type": type(smr_response).__name__,
                    "smr_response_preview": str(smr_response)[:500] if smr_response else None,
                },
            )

        logger.info(
            "SMR service returned TTS serviceId",
            extra={
                "service_id": smr_response.get("serviceId"),
                "tenant_id": smr_response.get("tenant_id"),
                "is_free_user": smr_response.get("is_free_user"),
                "tenant_policy": smr_response.get("tenant_policy"),
                "service_policy": smr_response.get("service_policy"),
                "scoring_details": smr_response.get("scoring_details"),
                "headers_used": bool(latency_policy or cost_policy or accuracy_policy),
                "smr_response_is_dict": isinstance(smr_response, dict),
                "smr_response_not_none": smr_response is not None,
            },
        )

        return smr_response

    except httpx.HTTPStatusError as e:
        logger.error(
            "SMR service returned error status for TTS",
            extra={"status_code": e.response.status_code, "response": e.response.text},
            exc_info=True,
        )
        # Try to extract structured error
        error_detail = None
        try:
            error_response = e.response.json()
            error_detail = error_response.get("detail", {})
        except (ValueError, KeyError):
            pass

        if error_detail and isinstance(error_detail, Dict) and error_detail.get("code") == "INVALID_POLICY_COMBINATION":
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
        logger.error("SMR service request failed for TTS", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SMR_SERVICE_UNAVAILABLE",
                "message": "SMR service is temporarily unavailable. Please try again.",
            },
        ) from e
    except Exception as e:
        logger.error("Unexpected error calling SMR service for TTS", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SMR_SERVICE_INTERNAL_ERROR",
                "message": f"Failed to call SMR service: {str(e)}",
            },
        ) from e


async def get_tts_service(
    tts_request: TTSInferenceRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_tenant_db_session)
) -> TTSService:
    """
    Dependency to get configured TTS service.
    
    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    The endpoint should be set in request.state by ensure_service_id_resolved dependency.
    """
    repository = TTSRepository(db)
    audio_service = AudioService()
    text_service = TextService()
    
    triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
    triton_api_key = getattr(http_request.app.state, "triton_api_key", "")
    triton_timeout = getattr(http_request.app.state, "triton_timeout", 300.0)
    
    print("DEBUG: TTS get_tts_service called", flush=True)
    logger.info(
        "TTS get_tts_service called",
        extra={
            "has_triton_endpoint": bool(triton_endpoint),
            "service_id_in_state": getattr(http_request.state, "service_id", None),
            "service_id_in_request": tts_request.config.serviceId if (tts_request and tts_request.config) else None,
            "triton_endpoint": triton_endpoint,
        }
    )
    
    # If endpoint not resolved, this means ensure_service_id_resolved failed
    # At this point, serviceId should already be in request.state (set by resolve_service_id_if_needed or ensure_service_id_resolved)
    # But if dependencies didn't run, try to get serviceId from request body
    if not triton_endpoint:
        # Try to get serviceId from request.state first (set by dependencies)
        service_id = getattr(http_request.state, "service_id", None)
        
        # If not in state, try to get from request body (fallback if dependencies didn't run)
        if not service_id and tts_request and tts_request.config and tts_request.config.serviceId:
            service_id = tts_request.config.serviceId
            logger.warning(
                "TTS: Dependencies may not have run, using serviceId from request body",
                extra={"service_id": service_id}
            )
        
        # If we have a serviceId but no endpoint, try to manually resolve it as fallback
        if service_id:
            model_management_client = getattr(http_request.app.state, "model_management_client", None)
            redis_client = getattr(http_request.app.state, "redis_client", None)
            
            if model_management_client:
                try:
                    # Extract auth headers
                    auth_headers: Dict[str, str] = {}
                    authorization = http_request.headers.get("Authorization") or http_request.headers.get("authorization")
                    if authorization:
                        auth_headers["Authorization"] = authorization
                    x_api_key = http_request.headers.get("X-API-Key") or http_request.headers.get("x-api-key")
                    if x_api_key:
                        auth_headers["X-API-Key"] = x_api_key
                    x_auth_source = http_request.headers.get("X-Auth-Source") or http_request.headers.get("x-auth-source")
                    if x_auth_source:
                        auth_headers["X-Auth-Source"] = x_auth_source
                    
                    logger.info(
                        "TTS: Manually resolving serviceId in get_tts_service",
                        extra={"service_id": service_id}
                    )
                    
                    service_info = await model_management_client.get_service(
                        service_id=service_id,
                        use_cache=True,
                        redis_client=redis_client,
                        auth_headers=auth_headers,
                    )
                    
                    if service_info and service_info.endpoint:
                        triton_endpoint = service_info.endpoint
                        triton_api_key = service_info.api_key or ""
                        
                        # Extract model name
                        triton_model_name = None
                        if service_info.model_inference_endpoint:
                            inference_endpoint = service_info.model_inference_endpoint
                            if isinstance(inference_endpoint, dict):
                                # First try top-level model_name (most common location)
                                triton_model_name = (
                                    inference_endpoint.get("model_name")
                                    or inference_endpoint.get("modelName")
                                    or inference_endpoint.get("model")
                                )
                                # Then try inside schema
                                if not triton_model_name:
                                    schema = inference_endpoint.get("schema", {})
                                    if isinstance(schema, dict):
                                        triton_model_name = (
                                            schema.get("model_name")
                                            or schema.get("modelName")
                                            or schema.get("name")
                                        )
                        if not triton_model_name:
                            triton_model_name = service_info.triton_model or service_info.model_name or "tts"
                        
                        logger.info(
                            "TTS: Extracted triton_model_name in get_tts_service",
                            extra={
                                "triton_model_name": triton_model_name,
                                "has_model_inference_endpoint": bool(service_info.model_inference_endpoint),
                                "triton_model": service_info.triton_model,
                                "model_name": service_info.model_name,
                            }
                        )
                        
                        http_request.state.triton_endpoint = triton_endpoint
                        http_request.state.triton_model_name = triton_model_name
                        http_request.state.service_id = service_id
                        if not getattr(http_request.app.state, "triton_api_key", None):
                            http_request.app.state.triton_api_key = triton_api_key
                        
                        logger.info(
                            "TTS: Successfully resolved serviceId in get_tts_service",
                            extra={
                                "service_id": service_id,
                                "triton_endpoint": triton_endpoint,
                                "triton_model_name": triton_model_name,
                            }
                        )
                    elif service_info:
                        http_request.state.model_management_error = f"Service {service_id} found but has no endpoint configured"
                    else:
                        http_request.state.model_management_error = f"Service {service_id} not found in Model Management database"
                except Exception as e:
                    logger.error(
                        "TTS: Error manually resolving serviceId in get_tts_service",
                        extra={"service_id": service_id, "error": str(e)},
                        exc_info=True,
                    )
                    http_request.state.model_management_error = str(e)
            
            # Check again if endpoint was resolved
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        if not triton_endpoint:
            # Try to get service_id from request.state (should be set by dependencies)
            service_id = getattr(http_request.state, "service_id", None)
            
            model_mgmt_error = getattr(http_request.state, "model_management_error", None)
            
            # Extract context for logging
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            
            if service_id:
                # Model Management failed to resolve endpoint for a specific serviceId
                logger.error(
                f"Model Management did not resolve serviceId: {service_id} and no default endpoint is allowed. Error: {model_mgmt_error}",
                extra={
                    "context": {
                        "error_type": "ModelUnavailableError",
                        "error_message": f"Model Management did not resolve serviceId: {service_id}",
                        "status_code": 500,
                        "service_id": service_id,
                        "model_management_error": model_mgmt_error,
                        "user_id": user_id,
                        "api_key_id": api_key_id,
                        "correlation_id": correlation_id,
                        "path": http_request.url.path,
                        "method": http_request.method,
                    }
                },
                exc_info=True
            )
            # Include more details in error message
            error_message = MODEL_UNAVAILABLE_TTS_MESSAGE
            if model_mgmt_error:
                if "not found" in model_mgmt_error.lower():
                    error_message = f"Service '{service_id}' not found in Model Management database. Please verify the serviceId is correct and the service is registered."
                elif "no endpoint" in model_mgmt_error.lower():
                    error_message = f"Service '{service_id}' found but has no endpoint configured. Please configure an endpoint for this service in Model Management."
                else:
                    error_message = f"{MODEL_UNAVAILABLE_TTS_MESSAGE} Details: {model_mgmt_error}"
            
            error_detail = ErrorDetail(
                message=error_message,
                code=MODEL_UNAVAILABLE,
            )
            raise HTTPException(
                status_code=500,
                detail=error_detail.dict(),
            )
        else:
            # Request is missing required serviceId
            # This should not happen if ensure_service_id_resolved ran correctly
            # Log for debugging
            logger.error(
                "TTS: No serviceId found and no endpoint resolved. This indicates ensure_service_id_resolved may have failed.",
                extra={
                    "service_id_in_state": getattr(http_request.state, "service_id", None),
                    "service_id_in_request": tts_request.config.serviceId if (tts_request and tts_request.config) else None,
                    "triton_endpoint": getattr(http_request.state, "triton_endpoint", None),
                }
            )
            
            # If still no endpoint, raise error
            if not triton_endpoint:
                error_detail = ErrorDetail(
                    message=INVALID_REQUEST_TTS_MESSAGE,
                    code=INVALID_REQUEST,
                )
                raise HTTPException(
                    status_code=400,
                    detail=error_detail.dict(),
                )
    
    model_name = getattr(http_request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(http_request.state, "service_id", None)
        model_mgmt_error = getattr(http_request.state, "model_management_error", None)
        
        # Extract context for logging
        correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        
        # Include more details in error message
        error_message = MODEL_UNAVAILABLE_TTS_MESSAGE
        if model_mgmt_error:
            if "not found" in model_mgmt_error.lower():
                error_message = f"Service '{service_id}' not found in Model Management database. Please verify the serviceId is correct and the service is registered."
            elif "no endpoint" in model_mgmt_error.lower():
                error_message = f"Service '{service_id}' found but has no endpoint configured. Please configure an endpoint for this service in Model Management."
            else:
                error_message = f"{MODEL_UNAVAILABLE_TTS_MESSAGE} Details: {model_mgmt_error}"
        
        error_detail = ErrorDetail(
            message=error_message,
            code=MODEL_UNAVAILABLE
        )
        logger.error(
            f"Model Management failed to resolve Triton model name for serviceId: {service_id}. Error: {model_mgmt_error}",
            extra={
                "context": {
                    "error_type": "ModelUnavailableError",
                    "error_message": f"Model Management failed to resolve Triton model name for serviceId: {service_id}",
                    "status_code": 500,
                    "service_id": service_id,
                    "triton_endpoint": triton_endpoint,
                    "model_management_error": model_mgmt_error,
                    "user_id": user_id,
                    "api_key_id": api_key_id,
                    "correlation_id": correlation_id,
                        "path": http_request.url.path,
                        "method": http_request.method,
                }
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail.dict(),
        )
    
    logger.info(
        "Using Triton endpoint=%s model_name=%s for serviceId=%s from Model Management",
        triton_endpoint,
        model_name,
        getattr(http_request.state, "service_id", "unknown"),
    )
    
    # Strip http:// or https:// scheme from URL if present (TritonClient expects host:port)
    triton_url = triton_endpoint
    if triton_url.startswith(('http://', 'https://')):
        triton_url = triton_url.split('://', 1)[1]
    
    triton_client = TritonClient(triton_url, triton_api_key)
    
    # Create TTS service
    return TTSService(repository, audio_service, text_service, triton_client)


async def ensure_service_id_resolved(
    request: TTSInferenceRequest,
    http_request: Request,
) -> None:
    """
    Dependency to ensure serviceId is resolved if provided directly in request body.
    This runs after resolve_service_id_if_needed to handle cases where serviceId
    is provided directly but Model Management middleware hasn't resolved it yet.
    
    Raises HTTPException if serviceId cannot be resolved.
    """
    print("DEBUG: TTS ensure_service_id_resolved dependency called", flush=True)
    logger.info(
        "TTS ensure_service_id_resolved dependency called",
        extra={
            "has_service_id": bool(request.config.serviceId),
            "service_id": request.config.serviceId,
            "has_triton_endpoint": bool(getattr(http_request.state, "triton_endpoint", None)),
        }
    )
    
    # If serviceId is provided directly and not yet resolved, manually resolve it
    if request.config.serviceId:
        service_id = request.config.serviceId
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        
        # Only resolve if not already resolved
        if not triton_endpoint:
            # Set service_id in request.state if not already set
            if not getattr(http_request.state, "service_id", None):
                http_request.state.service_id = service_id
            
            # Try to manually resolve using Model Management client
            model_management_client = getattr(http_request.app.state, "model_management_client", None)
            redis_client = getattr(http_request.app.state, "redis_client", None)
            
            if model_management_client:
                try:
                    # Extract auth headers
                    auth_headers: Dict[str, str] = {}
                    authorization = http_request.headers.get("Authorization") or http_request.headers.get("authorization")
                    if authorization:
                        auth_headers["Authorization"] = authorization
                    x_api_key = http_request.headers.get("X-API-Key") or http_request.headers.get("x-api-key")
                    if x_api_key:
                        auth_headers["X-API-Key"] = x_api_key
                    x_auth_source = http_request.headers.get("X-Auth-Source") or http_request.headers.get("x-auth-source")
                    if x_auth_source:
                        auth_headers["X-Auth-Source"] = x_auth_source
                    
                    logger.info(
                        "TTS: Manually resolving serviceId from request body",
                        extra={"service_id": service_id}
                    )
                    
                    service_info = await model_management_client.get_service(
                        service_id=service_id,
                        use_cache=True,
                        redis_client=redis_client,
                        auth_headers=auth_headers,
                    )
                    
                    if service_info and service_info.endpoint:
                        triton_endpoint = service_info.endpoint
                        triton_api_key = service_info.api_key or ""
                        
                        # Extract model name
                        triton_model_name = None
                        if service_info.model_inference_endpoint:
                            inference_endpoint = service_info.model_inference_endpoint
                            if isinstance(inference_endpoint, dict):
                                # First try top-level model_name (most common location)
                                triton_model_name = (
                                    inference_endpoint.get("model_name")
                                    or inference_endpoint.get("modelName")
                                    or inference_endpoint.get("model")
                                )
                                # Then try inside schema
                                if not triton_model_name:
                                    schema = inference_endpoint.get("schema", {})
                                    if isinstance(schema, dict):
                                        triton_model_name = (
                                            schema.get("model_name")
                                            or schema.get("modelName")
                                            or schema.get("name")
                                        )
                        if not triton_model_name:
                            triton_model_name = service_info.triton_model or service_info.model_name or "tts"
                        
                        logger.info(
                            "TTS: Extracted triton_model_name in ensure_service_id_resolved",
                            extra={
                                "triton_model_name": triton_model_name,
                                "has_model_inference_endpoint": bool(service_info.model_inference_endpoint),
                                "triton_model": service_info.triton_model,
                                "model_name": service_info.model_name,
                            }
                        )
                        
                        http_request.state.triton_endpoint = triton_endpoint
                        http_request.state.triton_model_name = triton_model_name
                        http_request.state.service_id = service_id
                        if not getattr(http_request.app.state, "triton_api_key", None):
                            http_request.app.state.triton_api_key = triton_api_key
                        
                        logger.info(
                            "TTS: Successfully resolved serviceId from request body",
                            extra={
                                "service_id": service_id,
                                "triton_endpoint": triton_endpoint,
                                "triton_model_name": triton_model_name,
                            }
                        )
                    elif service_info:
                        error_msg = f"Service {service_id} found but has no endpoint configured"
                        http_request.state.model_management_error = error_msg
                        logger.error(
                            "TTS: Service found but has no endpoint",
                            extra={"service_id": service_id}
                        )
                        raise HTTPException(
                            status_code=500,
                            detail={
                                "code": "MODEL_UNAVAILABLE",
                                "message": error_msg
                            }
                        )
                    else:
                        error_msg = f"Service {service_id} not found in Model Management database"
                        http_request.state.model_management_error = error_msg
                        logger.error(
                            "TTS: Service not found in Model Management",
                            extra={"service_id": service_id}
                        )
                        raise HTTPException(
                            status_code=500,
                            detail={
                                "code": "MODEL_UNAVAILABLE",
                                "message": error_msg
                            }
                        )
                except HTTPException:
                    # Re-raise HTTP exceptions
                    raise
                except Exception as e:
                    logger.error(
                        "TTS: Error manually resolving serviceId from request body",
                        extra={"service_id": service_id, "error": str(e)},
                        exc_info=True,
                    )
                    http_request.state.model_management_error = str(e)
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "code": "MODEL_MANAGEMENT_ERROR",
                            "message": f"Failed to resolve serviceId {service_id}: {str(e)}"
                        }
                    ) from e
            else:
                # Model Management client not available - this should have been caught earlier
                # but if we get here, raise an error
                logger.error(
                    "TTS: Model Management client not available for manual resolution",
                    extra={"service_id": service_id}
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "MODEL_MANAGEMENT_ERROR",
                        "message": "Model Management client not available"
                    }
                )


@inference_router.post(
    "/inference",
    response_model=TTSInferenceResponse,
    response_model_exclude_none=False,  # Include None values so smr_response is always present
    summary="Perform batch TTS inference",
    description="Convert text to speech for one or more text inputs"
)
async def run_inference(
    request: TTSInferenceRequest,
    http_request: Request,
    smr_response: Optional[Dict[str, Any]] = Depends(resolve_service_id_if_needed),
    _: None = Depends(ensure_service_id_resolved),  # Ensure serviceId is resolved if provided directly
    tts_service: TTSService = Depends(get_tts_service),
) -> TTSInferenceResponse:
    """
    Run TTS inference on the given request.
    
    Creates detailed trace spans for the entire inference operation.
    """
    logger.info(
        "TTS run_inference handler called",
        extra={
            "has_service_id": bool(request.config.serviceId if request and request.config else None),
            "service_id": request.config.serviceId if (request and request.config) else None,
            "smr_response": bool(smr_response),
            "has_tts_service": bool(tts_service),
        }
    )
    
    # Create a span for the entire inference operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _run_tts_inference_impl(request, http_request, tts_service)
    
    with tracer.start_as_current_span("tts.inference") as span:
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
            span.set_attribute("tts.input_count", len(request.input))
            span.set_attribute("tts.service_id", request.config.serviceId)
            span.set_attribute("tts.language", request.config.language.sourceLanguage)
            span.set_attribute("tts.gender", request.config.gender.value)
            span.set_attribute("tts.audio_format", request.config.audioFormat.value)
            if request.config.samplingRate:
                span.set_attribute("tts.sampling_rate", request.config.samplingRate)
            
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
            span.add_event("tts.inference.started", {
                "input_count": len(request.input),
                "service_id": request.config.serviceId,
                "language": request.config.language.sourceLanguage,
                "gender": request.config.gender.value,
                "smr_used": smr_response is not None,
            })

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
            
            logger.info(
                "Processing TTS inference request with %d text input(s), input_characters=%d, input_words=%d, user_id=%s api_key_id=%s session_id=%s",
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
                }
            )

            # Run inference
            response = await tts_service.run_inference(
                request=request,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            
            # Validate response is not None
            if response is None:
                logger.error("TTS service returned None response")
                span.set_attribute("error", True)
                span.set_attribute("error.type", "InvalidResponse")
                span.set_status(Status(StatusCode.ERROR, "TTS service returned None"))
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "TTS service returned an invalid response"
                    }
                )
            
            # Add response metadata
            span.set_attribute("tts.output_count", len(response.audio) if response.audio else 0)
            span.set_attribute("http.status_code", 200)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Calculate output metrics (audio duration) for successful responses
            total_output_audio_duration = 0.0
            total_output_audio_size = 0
            if response.audio:
                import base64
                for audio_output in response.audio:
                    try:
                        audio_bytes = base64.b64decode(audio_output.audioContent)
                        total_output_audio_size += len(audio_bytes)
                        # Estimate duration: assume 2 bytes per sample for 16-bit audio at target sample rate
                        target_sr = request.config.samplingRate or 22050
                        total_samples = len(audio_bytes) / 2
                        total_output_audio_duration += total_samples / target_sr
                    except Exception:
                        pass
            
            # Store output details in request.state for middleware to access
            http_request.state.output_details = {
                "audio_length_seconds": total_output_audio_duration,
                "audio_length_ms": total_output_audio_duration * 1000.0,
                "output_count": len(response.audio)
            }
            
            # Add output audio length to trace span
            span.set_attribute("tts.output.audio_length_seconds", total_output_audio_duration)
            span.set_attribute("tts.output.audio_length_ms", total_output_audio_duration * 1000.0)
            if total_output_audio_size > 0:
                span.set_attribute("tts.output.audio_size_bytes", total_output_audio_size)
            
            # Add span event for successful completion
            span.add_event("tts.inference.completed", {
                "output_count": len(response.audio),
                "output_audio_duration": total_output_audio_duration,
                "output_audio_length_seconds": total_output_audio_duration,
                "status": "success"
            })
            span.set_status(Status(StatusCode.OK))
            
            # Include SMR response in the final response (null if SMR was not called)
            smr_response_data = getattr(http_request.state, "smr_response_data", None)
            
            # Log SMR response retrieval for debugging
            logger.info(
                "TTS: Retrieving SMR response for final response",
                extra={
                    "has_smr_response_in_state": smr_response_data is not None,
                    "smr_service_id": smr_response_data.get("serviceId") if smr_response_data else None,
                    "smr_tenant_id": smr_response_data.get("tenant_id") if smr_response_data else None,
                    "smr_is_free_user": smr_response_data.get("is_free_user") if smr_response_data else None,
                    "smr_response_type": type(smr_response_data).__name__ if smr_response_data else None,
                },
            )
            
            # Use model_dump() for Pydantic v2, fallback to dict() for v1
            # Use exclude_none=False to ensure smr_response is included even if None
            if response is None:
                logger.error("TTS service returned None response")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "TTS service returned an invalid response"
                    }
                )
            
            try:
                # Pydantic v2
                response_dict = response.model_dump(exclude_none=False)
            except AttributeError:
                # Pydantic v1
                response_dict = response.dict(exclude_none=False)
            
            if not isinstance(response_dict, dict):
                logger.error(f"TTS service returned invalid response_dict type: {type(response_dict)}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "TTS service returned an invalid response format"
                    }
                )
            
            response_dict["smr_response"] = smr_response_data
            # Recreate response with smr_response included
            try:
                response = TTSInferenceResponse(**response_dict)
            except Exception as e:
                logger.error(
                    f"Failed to create TTSInferenceResponse from response_dict: {e}",
                    extra={
                        "response_dict_keys": list(response_dict.keys()) if isinstance(response_dict, dict) else None,
                        "response_dict_type": type(response_dict).__name__,
                        "smr_response_data": smr_response_data,
                    },
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": f"Failed to create response: {str(e)}"
                    }
                ) from e
            
            logger.info(
                "TTS: Final response prepared with SMR data",
                extra={
                    "has_smr_response": response.smr_response is not None,
                    "smr_service_id": response.smr_response.get("serviceId") if response.smr_response else None,
                },
            )
            
            logger.info(
                "TTS inference completed successfully, output_audio_duration=%.2fs",
                total_output_audio_duration,
                extra={
                    # Common input/output details structure (general fields for all services)
                    "input_details": {
                        "character_length": total_input_characters,
                        "word_count": total_input_words,
                        "input_count": len(request.input)
                    },
                    "output_details": {
                        "audio_length_seconds": total_output_audio_duration,
                        "audio_length_ms": total_output_audio_duration * 1000.0,
                        "output_count": len(response.audio)
                    },
                    # Service metadata (for filtering)
                    "service_id": request.config.serviceId,
                    "source_language": request.config.language.sourceLanguage,
                    "http_status_code": 200,
                }
            )
            return response

        except ValueError as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("tts.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Validation error in TTS inference: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc)
            ) from exc

        except Exception as exc:
            # Extract context for logging
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            session_id = getattr(http_request.state, "session_id", None)
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            # Get correlation ID for logging (already imported at top of file)
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            
            # Trace the error
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", getattr(exc, 'status_code', 500))
            if service_id:
                span.set_attribute("tts.service_id", service_id)
            if triton_endpoint:
                span.set_attribute("triton.endpoint", triton_endpoint)
            if model_name:
                span.set_attribute("triton.model_name", model_name)
            span.add_event("tts.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            
            # Log error with full context
            logger.error(
                f"TTS inference failed: {exc}",
                extra={
                    "context": {
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "service_id": service_id,
                        "triton_endpoint": triton_endpoint,
                        "model_name": model_name,
                        "user_id": user_id,
                        "api_key_id": api_key_id,
                        "session_id": session_id,
                        "correlation_id": correlation_id,
                        "input_count": len(request.input) if hasattr(request, 'input') else None,
                    }
                },
                exc_info=True
            )
            
            # Import service-specific exceptions
            from middleware.exceptions import (
                TritonInferenceError,
                ModelNotFoundError,
                ServiceUnavailableError,
                AudioProcessingError
            )
            
            # Check if it's already a service-specific error
            if isinstance(exc, (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError, AudioProcessingError)):
                raise
            
            # Check error type and raise appropriate exception
            error_msg = str(exc)
            if "unknown model" in error_msg.lower() or ("model" in error_msg.lower() and "not found" in error_msg.lower()):
                import re
                model_match = re.search(r"model: '([^']+)'", error_msg)
                model_name = model_match.group(1) if model_match else "tts"
                raise ModelNotFoundError(
                    message=f"Model '{model_name}' not found in Triton inference server. Please verify the model name and ensure it is loaded.",
                    model_name=model_name
                )
            elif "triton" in error_msg.lower() or "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                raise ServiceUnavailableError(
                    message=f"TTS service unavailable: {error_msg}. Please check Triton server connectivity."
                )
            elif "audio" in error_msg.lower():
                raise AudioProcessingError(f"Audio processing failed: {error_msg}")
            else:
                # Generic Triton error
                raise TritonInferenceError(
                    message=f"TTS inference failed: {error_msg}",
                    model_name="tts"
                )


async def _run_tts_inference_impl(
    request: TTSInferenceRequest,
    http_request: Request,
    tts_service: TTSService,
) -> TTSInferenceResponse:
    """Fallback implementation when tracing is not available."""
    # Validate request
    await validate_request(request)
    
    # Extract auth context from request.state
    user_id = getattr(http_request.state, 'user_id', None)
    api_key_id = getattr(http_request.state, 'api_key_id', None)
    session_id = getattr(http_request.state, 'session_id', None)
    
    logger.info(
        "Processing TTS inference request with %d text input(s), user_id=%s api_key_id=%s session_id=%s",
        len(request.input),
        user_id,
        api_key_id,
        session_id,
    )

    response = await tts_service.run_inference(
        request=request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id
    )
    
    # Include SMR response in the final response (null if SMR was not called)
    smr_response_data = getattr(http_request.state, "smr_response_data", None)
    
    if response is None:
        logger.error("TTS service returned None response")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "TTS service returned an invalid response"
            }
        )
    
    # Use model_dump() for Pydantic v2, fallback to dict() for v1
    # Use exclude_none=False to ensure smr_response is included even if None
    try:
        # Pydantic v2
        response_dict = response.model_dump(exclude_none=False)
    except AttributeError:
        # Pydantic v1
        response_dict = response.dict(exclude_none=False)
    
    if not isinstance(response_dict, dict):
        logger.error(f"TTS service returned invalid response_dict type: {type(response_dict)}")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "TTS service returned an invalid response format"
            }
        )
    
    response_dict["smr_response"] = smr_response_data
    # Recreate response with smr_response included
    try:
        response = TTSInferenceResponse(**response_dict)
    except Exception as e:
        logger.error(
            f"Failed to create TTSInferenceResponse from response_dict: {e}",
            extra={
                "response_dict_keys": list(response_dict.keys()) if isinstance(response_dict, dict) else None,
                "response_dict_type": type(response_dict).__name__,
                "smr_response_data": smr_response_data,
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_SERVER_ERROR",
                "message": f"Failed to create response: {str(e)}"
            }
        ) from e
    
    logger.info("TTS inference completed successfully")
    return response


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available TTS models",
    description="Get list of supported TTS models, languages, and voices"
)
async def list_models() -> Dict[str, Any]:
    """List available TTS models."""
    return {
        "models": [
            {
                "model_id": "indic-tts-coqui-dravidian",
                "languages": ["kn", "ml", "ta", "te"],
                "voices": ["male", "female"],
                "description": "Dravidian language TTS model"
            },
            {
                "model_id": "indic-tts-coqui-indo_aryan",
                "languages": ["hi", "bn", "gu", "mr", "pa"],
                "voices": ["male", "female"],
                "description": "Indo-Aryan language TTS model"
            },
            {
                "model_id": "indic-tts-coqui-misc",
                "languages": ["en", "brx", "mni"],
                "voices": ["male", "female"],
                "description": "Miscellaneous language TTS model"
            }
        ],
        "supported_languages": [
            "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
            "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai",
            "brx", "mni"
        ],
        "supported_voices": ["male", "female"],
        "supported_formats": ["wav", "mp3", "ogg", "pcm"],
        "supported_sample_rates": [8000, 16000, 22050, 44100, 48000]
    }


async def validate_request(request: TTSInferenceRequest) -> None:
    """Validate TTS inference request."""
    try:
        # Validate service ID only if provided (SMR will handle selection when missing)
        if request.config.serviceId:
            validate_service_id(request.config.serviceId)
        
        # Validate language code
        validate_language_code(request.config.language.sourceLanguage)
        
        # Validate gender
        validate_gender(request.config.gender.value)
        
        # Validate audio format
        validate_audio_format(request.config.audioFormat.value)
        
        # Validate sample rate
        if request.config.samplingRate:
            validate_sample_rate(request.config.samplingRate)
        
        # Validate text inputs
        for text_input in request.input:
            validate_text_input(text_input.source)
            
            # Validate audio duration if specified
            if text_input.audioDuration:
                validate_audio_duration(text_input.audioDuration)
        
    except (NoTextInputError, EmptyInputError, TextTooShortError, TextTooLongError, 
            InvalidCharactersError, LanguageMismatchError, InvalidLanguageCodeError,
            VoiceNotAvailableError, InvalidServiceIdError, InvalidGenderError,
            InvalidAudioFormatError, InvalidSampleRateError):
        # Re-raise specific validation exceptions directly (they will be caught by handlers above)
        raise
    except Exception as e:
        logger.warning(f"Request validation failed: {e}")
        raise ValueError(f"Invalid request: {e}")
