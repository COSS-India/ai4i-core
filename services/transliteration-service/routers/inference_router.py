"""
Inference Router
FastAPI router for transliteration inference endpoints
"""

import logging
import time
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from models.transliteration_request import TransliterationInferenceRequest
from models.transliteration_response import TransliterationInferenceResponse
from repositories.transliteration_repository import TransliterationRepository
from services.transliteration_service import TransliterationService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.model_management_client import ModelManagementClient
from utils.auth_utils import extract_auth_headers
from utils.validation_utils import (
    validate_language_pair, validate_service_id, validate_batch_size,
    InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError
)
from middleware.auth_provider import AuthProvider
from middleware.exceptions import AuthenticationError, AuthorizationError

# Observability: Dhruva plugin automatically extracts metrics from request body
# No manual recording needed - metrics are tracked automatically by middleware!

logger = logging.getLogger(__name__)

# Create router
inference_router = APIRouter(
    prefix="/api/v1/transliteration",
    tags=["Transliteration Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session"""
    return request.app.state.db_session_factory()


def create_triton_client(triton_url: str, api_key: str) -> TritonClient:
    """Factory function to create Triton client"""
    return TritonClient(triton_url=triton_url, api_key=api_key)


async def get_transliteration_service(request: Request, db: AsyncSession = Depends(get_db_session)) -> TransliterationService:
    """
    Dependency to get configured transliteration service
    
    Raises:
        HTTPException: If model management client is not available
    """
    repository = TransliterationRepository(db)
    text_service = TextService()
    
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
            detail="Model management service is not available. The transliteration service requires model management to operate."
        )
    
    redis_client = getattr(request.app.state, "redis_client", None)
    cache_ttl = getattr(request.app.state, "transliteration_endpoint_cache_ttl", 300)
    
    return TransliterationService(
        repository, 
        text_service,
        get_triton_client_for_endpoint,
        model_management_client,
        redis_client=redis_client,
        cache_ttl_seconds=cache_ttl
    )


@inference_router.post(
    "/inference",
    response_model=TransliterationInferenceResponse,
    summary="Perform batch transliteration inference",
    description="Transliterate text from source language to target language for one or more text inputs (max 100)"
)
async def run_inference(
    request: TransliterationInferenceRequest,
    http_request: Request,
    transliteration_service: TransliterationService = Depends(get_transliteration_service)
) -> TransliterationInferenceResponse:
    """Run transliteration inference on the given request"""
    try:
        # Validate request
        validate_service_id(request.config.serviceId)
        validate_language_pair(
            request.config.language.sourceLanguage,
            request.config.language.targetLanguage
        )
        validate_batch_size(len(request.input), max_size=100)
        
        # Validate top_k for sentence level
        if request.config.numSuggestions > 0 and request.config.isSentence:
            raise HTTPException(
                status_code=400, 
                detail="numSuggestions (top_k) is not valid for sentence level transliteration"
            )
        
        # Extract auth context from request.state
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_id = getattr(http_request.state, 'api_key_id', None)
        session_id = getattr(http_request.state, 'session_id', None)
        
        # Extract auth headers for model management service calls
        auth_headers = extract_auth_headers(http_request)
        
        # Log incoming request
        logger.info(f"Processing transliteration inference request with {len(request.input)} texts")
        
        # Run inference
        # Note: Dhruva Observability Plugin automatically extracts and records:
        # - Transliteration characters from request body
        # - Organization/app from JWT token or headers
        # - Request duration and status
        # No manual metric recording needed!
        response = await transliteration_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
            auth_headers=auth_headers
        )
        
        logger.info(f"Transliteration inference completed successfully")
        return response
        
    except (InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError) as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"Transliteration inference failed: {e}", exc_info=True)
        # Return more detailed error in development, generic in production
        import traceback
        error_detail = {
            "message": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc() if logger.level <= logging.DEBUG else None
        }
        raise HTTPException(status_code=500, detail=error_detail)


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available transliteration models",
    description="Get list of supported transliteration models and language pairs"
)
async def list_models() -> Dict[str, Any]:
    """List available transliteration models and language pairs"""
    return {
        "models": [
            {
                "model_id": "ai4bharat/indicxlit",
                "provider": "AI4Bharat",
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                    "mai", "brx", "mni", "sat", "gom"
                ],
                "description": "IndicXlit model supporting transliteration for 20+ Indic languages",
                "max_batch_size": 100,
                "supports_sentence_level": True,
                "supports_word_level": True,
                "supports_top_k": True
            }
        ],
        "total_models": 1
    }


@inference_router.get(
    "/services",
    response_model=Dict[str, Any],
    summary="List available transliteration services",
    description="Get list of supported transliteration services with their Triton endpoints"
)
async def list_services() -> Dict[str, Any]:
    """List available transliteration services and their endpoints"""
    return {
        "services": [
            {
                "service_id": "ai4bharat/indicxlit",
                "model_id": "ai4bharat/indicxlit",
                "triton_endpoint": "13.200.133.97:8000",
                "triton_model": "transliteration",
                "provider": "AI4Bharat",
                "description": "IndicXlit model supporting transliteration for 20+ Indic languages",
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                    "mai", "brx", "mni", "sat", "gom"
                ]
            },
            {
                "service_id": "indicxlit",
                "model_id": "ai4bharat/indicxlit",
                "triton_endpoint": "13.200.133.97:8000",
                "triton_model": "transliteration",
                "provider": "AI4Bharat",
                "description": "IndicXlit model supporting transliteration for 20+ Indic languages (alias)",
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                    "mai", "brx", "mni", "sat", "gom"
                ]
            }
        ],
        "total_services": 2
    }


@inference_router.get(
    "/languages",
    response_model=Dict[str, Any],
    summary="Get supported languages",
    description="Get list of supported languages for a specific transliteration model or service"
)
async def list_languages(
    model_id: Optional[str] = Query(None, description="Model ID to get languages for"),
    service_id: Optional[str] = Query(None, description="Service ID to get languages for")
) -> Dict[str, Any]:
    """List supported languages for a specific transliteration model or service"""
    
    # Service ID to Model ID mapping
    SERVICE_TO_MODEL_MAP = {
        "ai4bharat/indicxlit": "ai4bharat/indicxlit",
        "indicxlit": "ai4bharat/indicxlit"
    }
    
    # Log received parameters for debugging
    logger.info(f"list_languages called with service_id={service_id}, model_id={model_id}")
    
    # Determine model_id from service_id if provided
    if service_id:
        if service_id in SERVICE_TO_MODEL_MAP:
            model_id = SERVICE_TO_MODEL_MAP[service_id]
            logger.info(f"Mapped service_id '{service_id}' to model_id '{model_id}'")
        else:
            logger.warning(f"Service '{service_id}' not found in mapping")
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_id}' not found. Available services: {', '.join(SERVICE_TO_MODEL_MAP.keys())}"
            )
    
    # Default to IndicXlit model if neither provided
    if not model_id:
        model_id = "ai4bharat/indicxlit"
        logger.info(f"No model_id provided, defaulting to '{model_id}'")
    
    # Hardcoded language data by model_id
    if model_id == "ai4bharat/indicxlit":
        return {
            "model_id": "ai4bharat/indicxlit",
            "provider": "AI4Bharat",
            "supported_languages": [
                "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                "mai", "brx", "mni", "sat", "gom"
            ],
            "language_details": [
                {"code": "en", "name": "English"},
                {"code": "hi", "name": "Hindi"},
                {"code": "ta", "name": "Tamil"},
                {"code": "te", "name": "Telugu"},
                {"code": "kn", "name": "Kannada"},
                {"code": "ml", "name": "Malayalam"},
                {"code": "bn", "name": "Bengali"},
                {"code": "gu", "name": "Gujarati"},
                {"code": "mr", "name": "Marathi"},
                {"code": "pa", "name": "Punjabi"},
                {"code": "or", "name": "Odia"},
                {"code": "as", "name": "Assamese"},
                {"code": "ur", "name": "Urdu"},
                {"code": "sa", "name": "Sanskrit"},
                {"code": "ks", "name": "Kashmiri"},
                {"code": "ne", "name": "Nepali"},
                {"code": "sd", "name": "Sindhi"},
                {"code": "kok", "name": "Konkani"},
                {"code": "doi", "name": "Dogri"},
                {"code": "mai", "name": "Maithili"},
                {"code": "brx", "name": "Bodo"},
                {"code": "mni", "name": "Manipuri"},
                {"code": "sat", "name": "Santali"},
                {"code": "gom", "name": "Goan Konkani"}
            ],
            "total_languages": 24
        }
    else:
        raise HTTPException(
            status_code=404, 
            detail=f"Model '{model_id}' not found. Available models: ai4bharat/indicxlit"
        )

