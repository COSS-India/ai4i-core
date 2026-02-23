"""
FastAPI router for TTS inference endpoints.
"""

import logging
import os
import time
import traceback
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
from middleware.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ErrorDetail,
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
)
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
from middleware.tenant_context import try_get_tenant_context

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id

logger = logging.getLogger(__name__)

# SMR Service Configuration
SMR_ENABLED = os.getenv("SMR_ENABLED", "true").lower() == "true"
SMR_SERVICE_URL = os.getenv("SMR_SERVICE_URL", "http://smr-service:8097")

# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("tts-service")

# API Gateway URL for multi-tenant checks
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")


# Create router
# Enforce auth and permission checks on all routes (same as OCR and NMT)
inference_router = APIRouter(
    prefix="/api/v1/tts", 
    tags=["TTS Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


def count_words(text: str) -> int:
    """Count words in text"""
    try:
        words = [word for word in text.split() if word.strip()]
        return len(words)
    except Exception:
        return 0


async def resolve_service_id_if_needed(
    request: TTSInferenceRequest,
    http_request: Request,
) -> Optional[Dict[str, Any]]:
    """
    Dependency to resolve serviceId via SMR if not provided in request.
    This runs before get_tts_service to ensure serviceId is available.

    Returns SMR response data if SMR was called, None otherwise.
    """
    logger.info(
        "TTS resolve_service_id_if_needed dependency called",
        extra={
            "has_service_id": bool(request.config.serviceId),
            "service_id": request.config.serviceId,
        },
    )

    # Logic: First check if serviceId is in request body
    # If yes, use it (skip SMR) but still need to resolve endpoint
    # If no, call SMR to get serviceId (if SMR is enabled)
    
    # If serviceId is provided, set it in request.state and resolve endpoint manually
    # (middleware may have already done this, but we ensure it's done)
    if request.config.serviceId:
        service_id = request.config.serviceId
        http_request.state.service_id = service_id
        
        # Check if endpoint is already resolved by middleware
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        triton_model_name = getattr(http_request.state, "triton_model_name", None)
        
        # If not resolved, manually resolve it
        if not triton_endpoint or not triton_model_name:
            logger.info(
                "TTS: serviceId provided directly, manually resolving endpoint",
                extra={
                    "service_id": service_id,
                    "endpoint_already_resolved": bool(triton_endpoint),
                    "model_name_already_resolved": bool(triton_model_name),
                }
            )
            
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
                    authorization = http_request.headers.get("Authorization") or http_request.headers.get("authorization")
                    if authorization:
                        auth_headers["Authorization"] = authorization
                    x_api_key = http_request.headers.get("X-API-Key") or http_request.headers.get("x-api-key")
                    if x_api_key:
                        auth_headers["X-API-Key"] = x_api_key
                    x_auth_source = http_request.headers.get("X-Auth-Source") or http_request.headers.get("x-auth-source")
                    if x_auth_source:
                        auth_headers["X-Auth-Source"] = x_auth_source
                    
                    # Check if we should bypass cache
                    bypass_cache = os.getenv("BYPASS_CACHE", "false").lower() == "true"
                    
                    service_info = await model_management_client.get_service(
                        service_id=service_id,
                        use_cache=not bypass_cache,
                        redis_client=redis_client,
                        auth_headers=auth_headers,
                    )
                    
                    if bypass_cache:
                        logger.info(
                            f"TTS: Bypassed cache for service {service_id} - fetched fresh data from Model Management",
                            extra={"service_id": service_id}
                        )
                    
                    # Log the raw service_info to debug what we're getting
                    # Log the full model_inference_endpoint structure for debugging
                    inference_endpoint_json = None
                    if service_info and service_info.model_inference_endpoint:
                        try:
                            import json
                            if isinstance(service_info.model_inference_endpoint, dict):
                                inference_endpoint_json = json.dumps(service_info.model_inference_endpoint, indent=2)
                            else:
                                inference_endpoint_json = str(service_info.model_inference_endpoint)
                        except Exception:
                            inference_endpoint_json = str(service_info.model_inference_endpoint)
                    
                    logger.info(
                        f"TTS: Raw service_info from Model Management for service {service_id}",
                        extra={
                            "service_id": service_id,
                            "has_service_info": service_info is not None,
                            "service_info_endpoint": service_info.endpoint if service_info else None,
                            "service_info_triton_model": service_info.triton_model if service_info else None,
                            "service_info_model_name": service_info.model_name if service_info else None,
                            "model_inference_endpoint_full": inference_endpoint_json,
                            "service_info_model_name": service_info.model_name if service_info else None,
                            "has_model_inference_endpoint": bool(service_info.model_inference_endpoint) if service_info else False,
                            "model_inference_endpoint_type": type(service_info.model_inference_endpoint).__name__ if (service_info and service_info.model_inference_endpoint) else None,
                            "model_inference_endpoint_raw": str(service_info.model_inference_endpoint)[:1000] if (service_info and service_info.model_inference_endpoint) else None,
                        }
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
                        triton_model_name = None
                        
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
                        
                        if not triton_model_name:
                            triton_model_name = service_info.triton_model
                        if not triton_model_name:
                            triton_model_name = service_info.model_name
                        if not triton_model_name and service_id:
                            parts = service_id.split("/")
                            if len(parts) > 1:
                                model_part = parts[-1]
                                if "--" in model_part:
                                    triton_model_name = model_part.split("--")[0]
                                else:
                                    triton_model_name = model_part
                        if not triton_model_name:
                            triton_model_name = "unknown"
                            logger.warning(
                                f"Could not determine Triton model name for service {service_id}. "
                                f"Using 'unknown' - this may cause Triton inference to fail.",
                                extra={
                                    "service_id": service_id,
                                    "service_info_triton_model": service_info.triton_model,
                                    "service_info_model_name": service_info.model_name,
                                    "has_model_inference_endpoint": bool(service_info.model_inference_endpoint),
                                }
                            )
                        
                        # Log where the model name came from
                        inference_endpoint_debug = None
                        if service_info.model_inference_endpoint:
                            if isinstance(service_info.model_inference_endpoint, dict):
                                schema = service_info.model_inference_endpoint.get("schema", {})
                                inference_endpoint_debug = {
                                    "has_schema": isinstance(schema, dict),
                                    "schema_model_name": schema.get("model_name") if isinstance(schema, dict) else None,
                                    "schema_modelName": schema.get("modelName") if isinstance(schema, dict) else None,
                                    "schema_name": schema.get("name") if isinstance(schema, dict) else None,
                                    "top_level_model_name": service_info.model_inference_endpoint.get("model_name"),
                                    "top_level_modelName": service_info.model_inference_endpoint.get("modelName"),
                                    "top_level_model": service_info.model_inference_endpoint.get("model"),
                                    "full_structure": str(service_info.model_inference_endpoint)[:500],
                                }
                            else:
                                inference_endpoint_debug = {
                                    "type": type(service_info.model_inference_endpoint).__name__,
                                    "value": str(service_info.model_inference_endpoint)[:500],
                                }
                        
                        logger.info(
                            f"TTS: Resolved Triton model name '{triton_model_name}' for service {service_id} (direct serviceId)",
                            extra={
                                "service_id": service_id,
                                "triton_model_name": triton_model_name,
                                "inference_endpoint_debug": inference_endpoint_debug,
                                "cache_bypassed": bypass_cache,
                            }
                        )
                        
                        http_request.state.triton_endpoint = triton_endpoint
                        http_request.state.triton_model_name = triton_model_name
                        model_id_for_db = service_info.model_id or service_id
                        http_request.state.model_id = model_id_for_db
                        if not getattr(http_request.app.state, "triton_api_key", None):
                            http_request.app.state.triton_api_key = triton_api_key
                        
                        logger.info(
                            "TTS: Manually resolved Triton endpoint for directly-provided serviceId",
                            extra={
                                "service_id": service_id,
                                "model_id": model_id_for_db,
                                "triton_endpoint": triton_endpoint,
                                "triton_model_name": triton_model_name,
                                "has_api_key": bool(triton_api_key),
                            },
                        )
                except Exception as e:
                    logger.error(
                        "TTS: Error resolving Triton endpoint for directly-provided serviceId",
                        extra={"service_id": service_id, "error": str(e)},
                        exc_info=True,
                    )
                    http_request.state.model_management_error = str(e)
        
        # SMR was not called since serviceId was provided
        logger.info(
            "TTS: serviceId provided directly, skipping SMR",
            extra={
                "service_id": service_id,
                "endpoint_resolved": bool(getattr(http_request.state, "triton_endpoint", None)),
                "model_name_resolved": bool(getattr(http_request.state, "triton_model_name", None)),
            },
        )
        return None  # SMR was not called
    
    # serviceId not provided - call SMR
    if not request.config.serviceId:
        # Check if SMR is enabled
        if not SMR_ENABLED:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "SMR_DISABLED",
                    "message": "SMR is disabled and serviceId is required in request body",
                },
            )
        user_id = getattr(http_request.state, "user_id", None)
        
        # Only use tenant_id if it's explicitly in the JWT token, not from fallback lookup
        # Check JWT payload directly to see if tenant_id was in the token
        jwt_payload = getattr(http_request.state, "jwt_payload", None)
        tenant_id = None
        if jwt_payload and jwt_payload.get("tenant_id"):
            # tenant_id is explicitly in JWT token - use it
            tenant_id = jwt_payload.get("tenant_id")
            logger.info(
                "TTS: Using tenant_id from JWT token",
                extra={
                    "tenant_id": tenant_id,
                    "jwt_has_tenant_id": True,
                },
            )
        else:
            # No tenant_id in JWT token - don't use fallback tenant_id
            logger.info(
                "TTS: No tenant_id in JWT token, not using tenant_id for SMR call",
                extra={
                    "jwt_payload_keys": list(jwt_payload.keys()) if jwt_payload else None,
                    "jwt_has_tenant_id": False,
                },
            )

        logger.info(
            "TTS serviceId not provided, calling SMR service (dependency)",
            extra={
                "user_id": user_id,
                "tenant_id": tenant_id,
                "tenant_id_source": "jwt" if (jwt_payload and jwt_payload.get("tenant_id")) else "none",
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
            http_request.state.fallback_service_id = fallback_service_id
            logger.info(
                "TTS: Extracted fallback service ID from SMR response",
                extra={
                    "primary_service_id": service_id,
                    "fallback_service_id": fallback_service_id,
                }
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
                # Use proper header extraction to handle case-insensitive headers
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

                # Check if we should bypass cache (for debugging or after DB updates)
                # You can set BYPASS_CACHE=true in environment to force fresh fetch
                bypass_cache = os.getenv("BYPASS_CACHE", "false").lower() == "true"
                
                service_info = await model_management_client.get_service(
                    service_id=service_id,
                    use_cache=not bypass_cache,  # Bypass cache if flag is set
                    redis_client=redis_client,
                    auth_headers=auth_headers,
                )
                
                if bypass_cache:
                    logger.info(
                        f"TTS: Bypassed cache for service {service_id} - fetched fresh data from Model Management",
                        extra={"service_id": service_id}
                    )
                
                # Log the raw service_info to debug what we're getting
                logger.info(
                    f"TTS: Raw service_info from Model Management for service {service_id}",
                    extra={
                        "service_id": service_id,
                        "has_service_info": service_info is not None,
                        "service_info_endpoint": service_info.endpoint if service_info else None,
                        "service_info_triton_model": service_info.triton_model if service_info else None,
                        "service_info_model_name": service_info.model_name if service_info else None,
                        "has_model_inference_endpoint": bool(service_info.model_inference_endpoint) if service_info else False,
                        "model_inference_endpoint_type": type(service_info.model_inference_endpoint).__name__ if (service_info and service_info.model_inference_endpoint) else None,
                        "model_inference_endpoint_raw": str(service_info.model_inference_endpoint)[:1000] if (service_info and service_info.model_inference_endpoint) else None,
                    }
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
                            extra={
                                "service_id": service_id,
                                "service_info_triton_model": service_info.triton_model,
                                "service_info_model_name": service_info.model_name,
                                "has_model_inference_endpoint": bool(service_info.model_inference_endpoint),
                            }
                        )
                    
                    # Log where the model name came from for debugging
                    # Extract detailed info about model_inference_endpoint structure
                    inference_endpoint_debug = None
                    if service_info.model_inference_endpoint:
                        if isinstance(service_info.model_inference_endpoint, dict):
                            schema = service_info.model_inference_endpoint.get("schema", {})
                            inference_endpoint_debug = {
                                "has_schema": isinstance(schema, dict),
                                "schema_model_name": schema.get("model_name") if isinstance(schema, dict) else None,
                                "schema_modelName": schema.get("modelName") if isinstance(schema, dict) else None,
                                "schema_name": schema.get("name") if isinstance(schema, dict) else None,
                                "top_level_model_name": service_info.model_inference_endpoint.get("model_name"),
                                "top_level_modelName": service_info.model_inference_endpoint.get("modelName"),
                                "top_level_model": service_info.model_inference_endpoint.get("model"),
                                "full_structure": str(service_info.model_inference_endpoint)[:500],
                            }
                        else:
                            inference_endpoint_debug = {
                                "type": type(service_info.model_inference_endpoint).__name__,
                                "value": str(service_info.model_inference_endpoint)[:500],
                            }
                    
                    logger.info(
                        f"TTS: Resolved Triton model name '{triton_model_name}' for service {service_id}",
                        extra={
                            "service_id": service_id,
                            "triton_model_name": triton_model_name,
                            "source": (
                                "schema" if (service_info.model_inference_endpoint and 
                                           isinstance(service_info.model_inference_endpoint, dict) and
                                           isinstance(service_info.model_inference_endpoint.get("schema"), dict) and
                                           (service_info.model_inference_endpoint.get("schema", {}).get("model_name") or
                                            service_info.model_inference_endpoint.get("schema", {}).get("modelName") or
                                            service_info.model_inference_endpoint.get("schema", {}).get("name"))) else
                                "inference_endpoint" if (service_info.model_inference_endpoint and 
                                                         isinstance(service_info.model_inference_endpoint, dict) and
                                                         (service_info.model_inference_endpoint.get("model_name") or
                                                          service_info.model_inference_endpoint.get("modelName") or
                                                          service_info.model_inference_endpoint.get("model"))) else
                                "triton_model" if service_info.triton_model else
                                "model_name" if service_info.model_name else
                                "service_id" if (service_id and triton_model_name and triton_model_name != "tts") else
                                "fallback"
                            ),
                            "service_info_triton_model": service_info.triton_model,
                            "service_info_model_name": service_info.model_name,
                            "inference_endpoint_debug": inference_endpoint_debug,
                            "cache_bypassed": bypass_cache,
                        }
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


async def switch_to_fallback_service(
    request: TTSInferenceRequest,
    http_request: Request,
    fallback_service_id: str,
) -> None:
    """
    Switch to fallback service by resolving its endpoint and updating request state.
    
    Args:
        request: TTS inference request
        http_request: FastAPI request object
        fallback_service_id: Fallback service ID from SMR
    """
    logger.info(
        "TTS: Switching to fallback service",
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
        # Extract auth headers from request (case-insensitive)
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
        
        # Check if we should bypass cache (for debugging or after DB updates)
        bypass_cache = os.getenv("BYPASS_CACHE", "false").lower() == "true"
        
        service_info = await model_management_client.get_service(
            service_id=fallback_service_id,
            use_cache=not bypass_cache,  # Bypass cache if flag is set
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
        
        triton_endpoint = service_info.endpoint
        triton_api_key = service_info.api_key or ""
        
        # Extract model name (same logic as primary service resolution)
        triton_model_name = None
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
        if not triton_model_name:
            triton_model_name = service_info.triton_model
        if not triton_model_name:
            triton_model_name = service_info.model_name
        if not triton_model_name and fallback_service_id:
            parts = fallback_service_id.split("/")
            if len(parts) > 1:
                model_part = parts[-1]
                if "--" in model_part:
                    triton_model_name = model_part.split("--")[0]
                else:
                    triton_model_name = model_part
        if not triton_model_name:
            triton_model_name = "unknown"
        
        # Update request state with fallback service endpoint
        http_request.state.triton_endpoint = triton_endpoint
        http_request.state.triton_api_key = triton_api_key
        http_request.state.triton_model_name = triton_model_name
        http_request.state.using_fallback_service = True
        
        # Store model_id for database record
        model_id_for_db = service_info.model_id or fallback_service_id
        http_request.state.model_id = model_id_for_db
        
        logger.info(
            "TTS: Successfully switched to fallback service",
            extra={
                "fallback_service_id": fallback_service_id,
                "triton_endpoint": triton_endpoint,
                "triton_model_name": triton_model_name,
                "model_id": model_id_for_db,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "TTS: Failed to resolve fallback service endpoint",
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


async def call_smr_service(
    request_body: Dict[str, Any],
    user_id: Optional[str],
    tenant_id: Optional[str],
    http_request: Request,
) -> Dict[str, Any]:
    """
    Call SMR service to get serviceId for the TTS request.

    Mirrors ASR SMR integration but with task_type='tts'.
    """
    try:
        headers = dict(http_request.headers)
        latency_policy = headers.get("X-Latency-Policy") or headers.get("x-latency-policy")
        cost_policy = headers.get("X-Cost-Policy") or headers.get("x-cost-policy")
        accuracy_policy = headers.get("X-Accuracy-Policy") or headers.get("x-accuracy-policy")
        request_profiler_header = headers.get("X-Request-Profiler") or headers.get("x-request-profiler")

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
        if request_profiler_header:
            smr_headers["X-Request-Profiler"] = request_profiler_header

        logger.info(
            "Calling SMR service to get TTS serviceId",
            extra={
                "user_id": user_id,
                "tenant_id": tenant_id,
                "has_policy_headers": bool(latency_policy or cost_policy or accuracy_policy),
                "has_request_profiler": bool(request_profiler_header),
                "request_profiler_header": request_profiler_header,
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
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session)
) -> TTSService:
    """
    Dependency to get configured TTS service.
    
    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    repository = TTSRepository(db)
    audio_service = AudioService()
    text_service = TextService()
    
    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.app.state, "triton_api_key", "")
    triton_timeout = getattr(request.app.state, "triton_timeout", 300.0)
    
    if not triton_endpoint:
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        
        # Extract context for logging
        correlation_id = get_correlation_id(request) or getattr(request.state, "correlation_id", None)
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Trace the error if we're in a span context
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.type", "ModelUnavailableError")
                current_span.set_attribute("error.message", f"Model Management did not resolve serviceId: {service_id}")
                current_span.set_attribute("http.status_code", 500)
                current_span.set_status(Status(StatusCode.ERROR, f"Model Management did not resolve serviceId: {service_id}"))
                if service_id:
                    current_span.set_attribute("tts.service_id", service_id)
                if correlation_id:
                    current_span.set_attribute("correlation.id", correlation_id)
        except Exception:
            pass  # Don't fail if tracing fails
        
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
                        "path": request.url.path,
                        "method": request.method,
                    }
                },
                exc_info=True
            )
            error_detail = ErrorDetail(
                message=MODEL_UNAVAILABLE_TTS_MESSAGE,
                code=MODEL_UNAVAILABLE,
            )
            raise HTTPException(
                status_code=500,
                detail=error_detail.dict(),
            )
        else:
            # Request is missing required serviceId
            error_detail = ErrorDetail(
                message=INVALID_REQUEST_TTS_MESSAGE,
                code=INVALID_REQUEST,
            )
            raise HTTPException(
                status_code=400,
                detail=error_detail.dict(),
            )
    
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        
        # Extract context for logging
        correlation_id = get_correlation_id(request) or getattr(request.state, "correlation_id", None)
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        triton_endpoint = getattr(request.state, "triton_endpoint", None)
        
        # Trace the error if we're in a span context
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.type", "ModelUnavailableError")
                current_span.set_attribute("error.message", f"Model Management failed to resolve Triton model name for serviceId: {service_id}")
                current_span.set_attribute("http.status_code", 500)
                current_span.set_status(Status(StatusCode.ERROR, f"Model Management failed to resolve Triton model name for serviceId: {service_id}"))
                if service_id:
                    current_span.set_attribute("tts.service_id", service_id)
                if triton_endpoint:
                    current_span.set_attribute("triton.endpoint", triton_endpoint)
                if correlation_id:
                    current_span.set_attribute("correlation.id", correlation_id)
        except Exception:
            pass  # Don't fail if tracing fails
        
        error_detail = ErrorDetail(
            message=MODEL_UNAVAILABLE_TTS_MESSAGE,
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
                    "path": request.url.path,
                    "method": request.method,
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
        getattr(request.state, "service_id", "unknown"),
    )
    
    # Strip http:// or https:// scheme from URL if present (TritonClient expects host:port)
    triton_url = triton_endpoint
    if triton_url.startswith(('http://', 'https://')):
        triton_url = triton_url.split('://', 1)[1]
    
    triton_client = TritonClient(triton_url, triton_api_key)
    
    # Pass resolved model_name to TTS service
    return TTSService(repository, audio_service, text_service, triton_client, resolved_model_name=model_name)



async def _enforce_tenant_and_service_checks(http_request: Request, service_name: str = "tts"):
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
    # Increase timeout for production environments where network latency may be higher
    timeout_duration = float(os.getenv("SERVICE_CHECK_TIMEOUT", "10.0"))
    try:
        async with httpx.AsyncClient(timeout=timeout_duration) as client:
            svc_resp = await client.get(f"{API_GATEWAY_URL}/api/v1/multi-tenant/list/services", headers=headers)
            if svc_resp.status_code == 200:
                services = svc_resp.json().get("services", [])
                svc_entry = next((s for s in services if str(s.get("service_name")).lower() == service_name.lower()), None)
                if not svc_entry or not svc_entry.get("is_active", False):
                    raise HTTPException(status_code=503, detail=ErrorDetail(code=SERVICE_UNAVAILABLE, message="TTS service is not active at the moment.Please contact your administrator").dict())
            else:
                # Log detailed error information for debugging
                error_detail = {
                    "status_code": svc_resp.status_code,
                    "response_text": svc_resp.text[:500],  # Limit response text to 500 chars
                    "api_gateway_url": API_GATEWAY_URL,
                    "headers_present": bool(headers),
                    "has_auth_header": bool(headers.get("Authorization") or headers.get("authorization")),
                    "has_api_key": bool(headers.get("X-API-Key") or headers.get("x-api-key"))
                }
                logger.error(
                    f"TTS: API_GATEWAY /list/services returned non-200 status",
                    extra=error_detail
                )
                
                # Provide more specific error messages based on status code
                if svc_resp.status_code == 401:
                    error_message = "Authentication failed when checking service availability. Please verify your API key and token."
                elif svc_resp.status_code == 403:
                    error_message = "Access denied when checking service availability. Please verify your permissions."
                elif svc_resp.status_code == 404:
                    error_message = f"Service availability endpoint not found at {API_GATEWAY_URL}. Please contact your administrator."
                elif svc_resp.status_code >= 500:
                    error_message = f"API Gateway returned server error (status {svc_resp.status_code}). Please contact your administrator."
                else:
                    error_message = f"Cannot detect service availability (status {svc_resp.status_code}). Please contact your administrator."
                
                raise HTTPException(
                    status_code=503,
                    detail=ErrorDetail(code=SERVICE_UNAVAILABLE, message=error_message).dict()
                )
    except httpx.TimeoutException as e:
        logger.error(
            f"TTS: Timeout when checking service availability for '{service_name}'",
            extra={
                "api_gateway_url": API_GATEWAY_URL,
                "timeout": timeout_duration,
                "error": str(e)
            }
        )
        raise HTTPException(status_code=503, detail=ErrorDetail(code=SERVICE_UNAVAILABLE, message=SERVICE_UNAVAILABLE_TTS_MESSAGE).dict())
    except httpx.ConnectError as e:
        logger.error(
            f"TTS: Connection error when checking service availability for '{service_name}'",
            extra={
                "api_gateway_url": API_GATEWAY_URL,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=503,
            detail=ErrorDetail(
                code=SERVICE_UNAVAILABLE,
                message=f"Cannot connect to API Gateway at {API_GATEWAY_URL}. Please contact your administrator."
            ).dict()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to verify service active state for '{service_name}'",
            extra={
                "api_gateway_url": API_GATEWAY_URL,
                "error_type": type(e).__name__,
                "error": str(e)
            },
            exc_info=True
        )
        raise HTTPException(status_code=503, detail=ErrorDetail(code=SERVICE_UNAVAILABLE, message=SERVICE_UNAVAILABLE_TTS_MESSAGE).dict())

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


async def enforce_tts_checks(request: Request):
    """FastAPI dependency that enforces tenant and service checks for TTS before other dependencies run."""
    # the service name is coming from multitenant SubscriptionType enum
    await _enforce_tenant_and_service_checks(request, service_name="tts")

# Add as a router-level dependency so it runs before path-operation dependencies like get_tts_service
inference_router.dependencies.append(Depends(enforce_tts_checks))


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
    tts_service: TTSService = Depends(get_tts_service)
) -> TTSInferenceResponse:
    """
    Run TTS inference on the given request.
    
    Creates detailed trace spans for the entire inference operation.
    """
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
                "gender": request.config.gender.value
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
            
            # Log removed - middleware handles request/response logging

            # Get fallback service ID from request state
            fallback_service_id = getattr(http_request.state, "fallback_service_id", None)
            using_fallback = False
            original_service_id = request.config.serviceId
            
            # Run inference with auth context - with fallback support
            try:
                response = await tts_service.run_inference(
                    request=request,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id,
                    http_request_state=http_request.state
                )
            except (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError) as primary_error:
                # Primary service failed - try fallback if available and different from primary
                if fallback_service_id and fallback_service_id != original_service_id:
                    logger.warning(
                        "TTS: Primary service failed, attempting fallback",
                        extra={
                            "primary_service_id": original_service_id,
                            "fallback_service_id": fallback_service_id,
                            "error_type": type(primary_error).__name__,
                            "error_message": str(primary_error),
                        },
                        exc_info=True
                    )
                    
                    # Add span event for fallback trigger if tracing is available
                    try:
                        current_span = trace.get_current_span()
                        if current_span and current_span.is_recording():
                            current_span.add_event("tts.fallback.triggered", {
                                "primary_service_id": original_service_id,
                                "fallback_service_id": fallback_service_id,
                                "error_type": type(primary_error).__name__,
                            })
                    except Exception:
                        pass
                    
                    try:
                        # Switch to fallback service
                        await switch_to_fallback_service(
                            request=request,
                            http_request=http_request,
                            fallback_service_id=fallback_service_id,
                        )
                        
                        # Create new TTS service with fallback endpoint
                        from repositories.tts_repository import TTSRepository
                        from services.audio_service import AudioService
                        from services.text_service import TextService
                        from utils.triton_client import TritonClient
                        from middleware.tenant_db_dependency import get_tenant_db_session
                        
                        triton_endpoint = getattr(http_request.state, "triton_endpoint")
                        triton_api_key = getattr(http_request.state, "triton_api_key", "")
                        triton_model_name = getattr(http_request.state, "triton_model_name", "tts")
                        
                        # Strip http:// or https:// scheme from URL if present
                        triton_url = triton_endpoint
                        if triton_url.startswith(('http://', 'https://')):
                            triton_url = triton_url.split('://', 1)[1]
                        
                        fallback_triton_client = TritonClient(triton_url, triton_api_key)
                        
                        # Get database session for fallback service
                        fallback_db = await get_tenant_db_session(http_request)
                        fallback_repository = TTSRepository(fallback_db)
                        fallback_audio_service = AudioService()
                        fallback_text_service = TextService()
                        fallback_tts_service = TTSService(
                            fallback_repository,
                            fallback_audio_service,
                            fallback_text_service,
                            fallback_triton_client,
                            resolved_model_name=triton_model_name
                        )
                        
                        # Retry inference with fallback service
                        logger.info(
                            "TTS: Retrying inference with fallback service",
                            extra={"fallback_service_id": fallback_service_id}
                        )
                        
                        response = await fallback_tts_service.run_inference(
                            request=request,
                            user_id=user_id,
                            api_key_id=api_key_id,
                            session_id=session_id,
                            http_request_state=http_request.state
                        )
                        
                        using_fallback = True
                        
                        # Add span event for fallback success if tracing is available
                        try:
                            current_span = trace.get_current_span()
                            if current_span and current_span.is_recording():
                                current_span.add_event("tts.fallback.success", {
                                    "fallback_service_id": fallback_service_id,
                                })
                                current_span.set_attribute("tts.fallback_used", True)
                                current_span.set_attribute("tts.fallback_service_id", fallback_service_id)
                        except Exception:
                            pass
                        
                        logger.info(
                            "TTS: Fallback service succeeded",
                            extra={"fallback_service_id": fallback_service_id}
                        )
                        
                    except Exception as fallback_error:
                        # Fallback also failed - create detailed error message
                        primary_error_msg = str(primary_error)
                        fallback_error_msg = str(fallback_error)
                        primary_error_type = type(primary_error).__name__
                        fallback_error_type = type(fallback_error).__name__
                        
                        logger.error(
                            "TTS: Both primary and fallback services failed",
                            extra={
                                "primary_service_id": original_service_id,
                                "fallback_service_id": fallback_service_id,
                                "primary_error_type": primary_error_type,
                                "primary_error": primary_error_msg,
                                "fallback_error_type": fallback_error_type,
                                "fallback_error": fallback_error_msg,
                            },
                            exc_info=True
                        )
                        
                        # Add span event for fallback failure if tracing is available
                        try:
                            current_span = trace.get_current_span()
                            if current_span and current_span.is_recording():
                                current_span.add_event("tts.fallback.failed", {
                                    "primary_service_id": original_service_id,
                                    "fallback_service_id": fallback_service_id,
                                    "primary_error_type": primary_error_type,
                                    "fallback_error_type": fallback_error_type,
                                })
                        except Exception:
                            pass
                        
                        # Store error details in request state for error handler to access
                        http_request.state.fallback_failure_details = {
                            "primary_service_id": original_service_id,
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
                        combined_error_message = (
                            f"Primary service ({original_service_id}) failed: {primary_error_msg}. "
                            f"Fallback service ({fallback_service_id}) also failed: {fallback_error_msg}"
                        )
                        raise TritonInferenceError(combined_error_message) from fallback_error
                else:
                    # No fallback available - re-raise original error
                    raise
            
            # Add response metadata
            span.set_attribute("tts.output_count", len(response.audio))
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
            # Log removed - middleware handles request/response logging
            
            # Include SMR response in the final response (null if SMR was not called)
            smr_response_data = getattr(http_request.state, "smr_response_data", None)
            
            # Update SMR response with fallback information if fallback was used
            if smr_response_data:
                if using_fallback:
                    # Create a copy to avoid modifying the original
                    smr_response_data = smr_response_data.copy()
                    smr_response_data["fallback_used"] = True
                    original_service_id_from_smr = smr_response_data.get("serviceId")
                    smr_response_data["original_service_id"] = original_service_id_from_smr
                    smr_response_data["serviceId"] = fallback_service_id
                    smr_response_data["fallback_service_id"] = fallback_service_id
                    smr_response_data["fallback_message"] = (
                        f"The service ID selected by SMR was '{original_service_id_from_smr}' but it didn't work. "
                        f"Fallback service ID '{fallback_service_id}' is used instead."
                    )
                    logger.info(
                        "TTS: Including SMR response with fallback usage",
                        extra={
                            "original_service_id": original_service_id_from_smr,
                            "fallback_service_id": fallback_service_id,
                            "fallback_message": smr_response_data["fallback_message"],
                        }
                    )
                else:
                    # Ensure fallback_used is False if not used
                    smr_response_data = smr_response_data.copy()
                    smr_response_data["fallback_used"] = False
            
            # Log SMR response retrieval for debugging
            logger.info(
                "TTS: Retrieving SMR response for final response",
                extra={
                    "has_smr_response_in_state": smr_response_data is not None,
                    "smr_service_id": smr_response_data.get("serviceId") if smr_response_data else None,
                    "smr_tenant_id": smr_response_data.get("tenant_id") if smr_response_data else None,
                    "smr_is_free_user": smr_response_data.get("is_free_user") if smr_response_data else None,
                    "smr_response_type": type(smr_response_data).__name__ if smr_response_data else None,
                    "using_fallback": using_fallback,
                    "fallback_service_id": fallback_service_id if using_fallback else None,
                },
            )
            
            # Use model_dump() for Pydantic v2, fallback to dict() for v1
            # Use exclude_none=False to ensure smr_response is included even if None
            try:
                # Pydantic v2
                response_dict = response.model_dump(exclude_none=False)
            except AttributeError:
                # Pydantic v1
                response_dict = response.dict(exclude_none=False)
            
            response_dict["smr_response"] = smr_response_data
            # Recreate response with smr_response included
            response = TTSInferenceResponse(**response_dict)
            
            logger.info(
                "TTS: Final response prepared with SMR data",
                extra={
                    "has_smr_response": response.smr_response is not None,
                    "smr_service_id": response.smr_response.get("serviceId") if response.smr_response else None,
                },
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
            
            # Import AudioProcessingError if not already imported
            from middleware.exceptions import AudioProcessingError
            
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
    
    # Log removed - middleware handles request/response logging

    response = await tts_service.run_inference(
        request=request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id
    )
    
    # Log removed - middleware handles request/response logging
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
