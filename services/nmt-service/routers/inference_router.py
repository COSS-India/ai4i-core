"""
Inference Router
FastAPI router for NMT inference endpoints
"""

import logging
import time
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.nmt_request import NMTInferenceRequest
from models.nmt_response import NMTInferenceResponse
from repositories.nmt_repository import NMTRepository
from services.nmt_service import NMTService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.model_management_client import ModelManagementClient
from utils.auth_utils import extract_auth_headers
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

# Import OpenTelemetry for manual span creation
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

logger = logging.getLogger(__name__)

# Create router
inference_router = APIRouter(
    prefix="/api/v1/nmt",
    tags=["NMT Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session"""
    return request.app.state.db_session_factory()


def create_triton_client(triton_url: str, api_key: str) -> TritonClient:
    """Factory function to create Triton client"""
    return TritonClient(triton_url=triton_url, api_key=api_key)


async def get_nmt_service(request: Request, db: AsyncSession = Depends(get_db_session)) -> NMTService:
    """Dependency to get configured NMT service"""
    repository = NMTRepository(db)
    text_service = TextService()
    
    # Default Triton client
    default_triton_client = None
    if getattr(request.app.state, "triton_endpoint", None):
        default_triton_client = TritonClient(
            triton_url=request.app.state.triton_endpoint,
            api_key=request.app.state.triton_api_key
        )
    
    # Factory function to create Triton clients for different endpoints
    def get_triton_client_for_endpoint(endpoint: str) -> TritonClient:
        """Create Triton client for specific endpoint"""
        # Use default API key for now (can be extended to support per-endpoint keys)
        return TritonClient(
            triton_url=endpoint,
            api_key=request.app.state.triton_api_key
        )
    
    # Get model management client from app state
    model_management_client = getattr(request.app.state, "model_management_client", None)
    redis_client = getattr(request.app.state, "redis_client", None)
    cache_ttl = getattr(request.app.state, "triton_endpoint_cache_ttl", 300)
    
    return NMTService(
        repository, 
        text_service, 
        default_triton_client,
        get_triton_client_for_endpoint,
        model_management_client=model_management_client,
        redis_client=redis_client,
        cache_ttl_seconds=cache_ttl
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
    nmt_service: NMTService = Depends(get_nmt_service)
) -> NMTInferenceResponse:
    """Run NMT inference on the given request"""
    # Create a descriptive span for NMT inference
    if TRACING_AVAILABLE:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("NMT Inference") as span:
            span.set_attribute("service.name", "nmt")
            span.set_attribute("service.type", "translation")
            span.set_attribute("nmt.input_count", len(request.input))
            span.set_attribute("nmt.service_id", request.config.serviceId)
            span.set_attribute("nmt.source_language", request.config.language.sourceLanguage)
            span.set_attribute("nmt.target_language", request.config.language.targetLanguage)
            return await _run_nmt_inference_internal(request, http_request, nmt_service)
    else:
        return await _run_nmt_inference_internal(request, http_request, nmt_service)


async def _run_nmt_inference_internal(request: NMTInferenceRequest, http_request: Request, nmt_service: NMTService) -> NMTInferenceResponse:
    """Internal NMT inference logic."""
    try:
        # Validate request
        validate_service_id(request.config.serviceId)
        validate_language_pair(
            request.config.language.sourceLanguage,
            request.config.language.targetLanguage
        )
        validate_batch_size(len(request.input))
        
        # Extract auth context from request.state
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_id = getattr(http_request.state, 'api_key_id', None)
        session_id = getattr(http_request.state, 'session_id', None)
        
        # Extract auth headers from incoming request to forward to model management service
        auth_headers = extract_auth_headers(http_request)
        
        # Log incoming request
        logger.info(f"Processing NMT inference request with {len(request.input)} texts")
        
        # Run inference
        response = await nmt_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
            auth_headers=auth_headers
        )
        
        logger.info(f"NMT inference completed successfully")
        return response
        
    except (InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError) as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError, TextProcessingError) as e:
        # Re-raise service-specific errors (they will be handled by error handler middleware)
        raise
    
    except Exception as e:
        logger.error(f"NMT inference failed: {e}", exc_info=True)
        # Check if it's a Triton-related error
        error_msg = str(e)
        if "unknown model" in error_msg.lower() or "model" in error_msg.lower() and "not found" in error_msg.lower():
            import re
            model_match = re.search(r"model: '([^']+)'", error_msg)
            model_name = model_match.group(1) if model_match else "unknown"
            raise ModelNotFoundError(
                message=f"Model '{model_name}' not found in Triton inference server. Please verify the model name and ensure it is loaded.",
                model_name=model_name
            )
        elif "triton" in error_msg.lower() or "connection" in error_msg.lower():
            raise ServiceUnavailableError(
                message=f"NMT service unavailable: {error_msg}. Please check Triton server connectivity."
            )
        else:
            # Generic error - wrap in TextProcessingError
            raise TextProcessingError(f"NMT inference failed: {error_msg}")
