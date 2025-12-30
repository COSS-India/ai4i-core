"""
Inference router for OCR service.

Exposes a ULCA-style OCR inference endpoint:
- POST /api/v1/ocr/inference
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from models.ocr_request import OCRInferenceRequest
from models.ocr_response import OCRInferenceResponse
from services.ocr_service import OCRService
from utils.triton_client import TritonClient, TritonInferenceError
from utils.validation_utils import validate_service_id, validate_language_code, InvalidServiceIdError, InvalidLanguageCodeError
from ai4icore_model_management import ModelManagementClient, extract_auth_headers
from middleware.auth_provider import AuthProvider

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/ocr",
    tags=["OCR Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_ocr_service(request: Request) -> OCRService:
    """
    Dependency to get configured OCR service
    
    Raises:
        HTTPException: If model management client is not available
    """
    # Factory function to create Triton clients for different endpoints
    def get_triton_client_for_endpoint(endpoint: str) -> TritonClient:
        """Create Triton client for specific endpoint"""
        # Get default API key from app state (can be overridden per-service from model management)
        default_api_key = getattr(request.app.state, "triton_api_key", "")
        return TritonClient(
            triton_url=endpoint,
            api_key=default_api_key
        )
    
    # Get model management client from app state (REQUIRED)
    model_management_client = getattr(request.app.state, "model_management_client", None)
    if model_management_client is None:
        logger.error("Model management client not available. Service cannot start without it.")
        raise HTTPException(
            status_code=503,
            detail="Model management service is not available. The OCR service requires model management to operate."
        )
    
    redis_client = getattr(request.app.state, "redis_client", None)
    cache_ttl = getattr(request.app.state, "ocr_endpoint_cache_ttl", 300)
    
    return OCRService(
        get_triton_client_for_endpoint,
        model_management_client,
        redis_client=redis_client,
        cache_ttl_seconds=cache_ttl
    )


@inference_router.post(
    "/inference",
    response_model=OCRInferenceResponse,
    summary="Perform batch OCR inference",
    description="Run OCR on one or more images using Surya OCR via Triton.",
)
async def run_inference(
    request: OCRInferenceRequest,
    http_request: Request,
    ocr_service: OCRService = Depends(get_ocr_service),
) -> OCRInferenceResponse:
    """
    Run OCR inference for a batch of images.
    """
    try:
        # Validate request
        validate_service_id(request.config.serviceId)
        validate_language_code(request.config.language.sourceLanguage)
        
        # Extract auth context from request.state (if middleware is configured)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        session_id = getattr(http_request.state, "session_id", None)
        
        # Extract auth headers for model management service calls
        auth_headers = extract_auth_headers(http_request)

        logger.info(
            "Processing OCR inference request with %d image(s), user_id=%s api_key_id=%s session_id=%s",
            len(request.image),
            user_id,
            api_key_id,
            session_id,
        )

        # Run inference (Triton + Surya OCR)
        response = await ocr_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
            auth_headers=auth_headers
        )
        logger.info("OCR inference completed successfully")
        return response

    except (InvalidServiceIdError, InvalidLanguageCodeError) as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except ValueError as e:
        # Handle service ID not found errors from model management service
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
            logger.warning(f"Service ID not found: {e}")
            raise HTTPException(
                status_code=404,
                detail=f"Service ID '{request.config.serviceId}' not found. Please verify the service ID is correct and registered in the model management service."
            )
        elif "endpoint" in error_msg.lower() and ("not configured" in error_msg.lower() or "no endpoint" in error_msg.lower()):
            logger.warning(f"Service endpoint not configured: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Service ID '{request.config.serviceId}' has no endpoint configured. Please configure the endpoint in the model management service."
            )
        else:
            logger.warning(f"Validation error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    except TritonInferenceError as e:
        error_msg = str(e)
        logger.error(f"OCR Triton inference failed: {e}", exc_info=True)
        
        # Service ID not found errors
        if "service" in error_msg.lower() and ("not found" in error_msg.lower() or "does not exist" in error_msg.lower()):
            raise HTTPException(
                status_code=404,
                detail=f"Service ID '{request.config.serviceId}' not found. Please verify the service ID is correct and registered."
            )
        
        # Triton endpoint errors
        if "not found" in error_msg.lower() or "404" in error_msg:
            raise HTTPException(
                status_code=404,
                detail=f"Triton model not found: {error_msg}"
            )
        elif "connect" in error_msg.lower() or "connection" in error_msg.lower() or "refused" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to Triton server: {error_msg}"
            )
        elif "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=504,
                detail=f"Triton inference request timed out: {error_msg}"
            )
        else:
            raise HTTPException(
                status_code=503,
                detail=f"Triton inference error: {error_msg}"
            )
    
    except Exception as e:  # pragma: no cover - generic error path
        logger.error(f"OCR inference failed: {e}", exc_info=True)
        error_msg = str(e)
        
        # Service ID not found errors
        if "service" in error_msg.lower() and ("not found" in error_msg.lower() or "does not exist" in error_msg.lower()):
            raise HTTPException(
                status_code=404,
                detail=f"Service ID '{request.config.serviceId}' not found. Please verify the service ID is correct and registered."
            )
        
        # Triton endpoint errors
        if "Triton" in error_msg or "triton" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail=f"Triton inference error: {error_msg}"
            )
        
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {error_msg}"
        )


