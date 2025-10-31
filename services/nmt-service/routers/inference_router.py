"""
Inference Router
FastAPI router for NMT inference endpoints
"""

import logging
import time
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from models.nmt_request import NMTInferenceRequest
from models.nmt_response import NMTInferenceResponse
from repositories.nmt_repository import NMTRepository
from services.nmt_service import NMTService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.validation_utils import (
    validate_language_pair, validate_service_id, validate_batch_size,
    InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError
)
from middleware.auth_provider import AuthProvider
from middleware.exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)

# Create router
inference_router = APIRouter(
    prefix="/api/v1/nmt",
    tags=["NMT Inference"],
    # dependencies=[Depends(AuthProvider)]  # Commented out for testing
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
    
    return NMTService(
        repository, 
        text_service, 
        default_triton_client,
        get_triton_client_for_endpoint
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
        
        # Log incoming request
        logger.info(f"Processing NMT inference request with {len(request.input)} texts")
        
        # Run inference
        response = await nmt_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        
        logger.info(f"NMT inference completed successfully")
        return response
        
    except (InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError) as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"NMT inference failed: {e}", exc_info=True)
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
    summary="List available NMT models",
    description="Get list of supported NMT models and language pairs"
)
async def list_models() -> Dict[str, Any]:
    """List available NMT models and language pairs"""
    return {
        "models": [
            {
                "model_id": "ai4bharat/indictrans-v2-all-gpu--t4",
                "provider": "AI4Bharat",
                "supported_languages": [
                    "en", "gom", "gu", "sa", "te", "mr", "hi", "or", "mni", 
                    "ml", "as", "doi", "sat", "ta", "sd", "bn", "ks", "kn", "ne"
                ],
                "description": "IndicTrans2 model supporting 19 Indian languages with bidirectional translation",
                "max_batch_size": 90,
                "supported_scripts": ["Deva", "Arab", "Taml", "Telu", "Knda", "Mlym", "Beng", "Gujr", "Guru", "Orya", "Latn"]
            },
            {
                "model_id": "facebook/nllb-200-1.3B",
                "provider": "Meta AI",
                "supported_languages": [
                    "en", "sw", "yo", "ha", "so", "am", "ti", "ig", "zu", "xh", 
                    "sn", "rw", "om", "lg", "wo", "ts", "tn", "af", "fr", "ar"
                ],
                "description": "NLLB-200 is Meta AI's state-of-the-art multilingual neural machine translation model with 1.3B parameters, supporting 200 languages across 24+ writing systems. This deployment focuses on African languages including Swahili, Yoruba, Hausa, Somali, Amharic, Tigrinya, and many others.",
                "max_batch_size": 90,
                "supported_scripts": ["Latn", "Ethi", "Arab"]
            }
        ],
        "total_models": 2
    }


@inference_router.get(
    "/services",
    response_model=Dict[str, Any],
    summary="List available NMT services",
    description="Get list of supported NMT services with their Triton endpoints"
)
async def list_services() -> Dict[str, Any]:
    """List available NMT services and their endpoints"""
    return {
        "services": [
            {
                "service_id": "ai4bharat/indictrans--gpu-t4",
                "model_id": "ai4bharat/indictrans-v2-all-gpu--t4",
                "triton_endpoint": "13.200.133.97:8000",
                "triton_model": "nmt",
                "provider": "AI4Bharat",
                "description": "IndicTrans2 model supporting 19 Indian languages",
                "supported_languages": [
                    "en", "gom", "gu", "sa", "te", "mr", "hi", "or", "mni", 
                    "ml", "as", "doi", "sat", "ta", "sd", "bn", "ks", "kn", "ne"
                ]
            },
            {
                "service_id": "indictrans-v2-all",
                "model_id": "ai4bharat/indictrans-v2-all-gpu--t4",
                "triton_endpoint": "13.200.133.97:8000",
                "triton_model": "nmt",
                "provider": "AI4Bharat",
                "description": "IndicTrans2 model supporting 19 Indian languages",
                "supported_languages": [
                    "en", "gom", "gu", "sa", "te", "mr", "hi", "or", "mni", 
                    "ml", "as", "doi", "sat", "ta", "sd", "bn", "ks", "kn", "ne"
                ]
            },
            {
                "service_id": "ai4bharat/indictrans-v2-all-gpu",
                "model_id": "ai4bharat/indictrans-v2-all-gpu--t4",
                "triton_endpoint": "13.200.133.97:8000",
                "triton_model": "nmt",
                "provider": "AI4Bharat",
                "description": "IndicTrans2 model supporting 19 Indian languages",
                "supported_languages": [
                    "en", "gom", "gu", "sa", "te", "mr", "hi", "or", "mni", 
                    "ml", "as", "doi", "sat", "ta", "sd", "bn", "ks", "kn", "ne"
                ]
            },
            {
                "service_id": "translnew2",
                "model_id": "facebook/nllb-200-1.3B",
                "triton_endpoint": "3.110.118.163:8000",
                "triton_model": "nmt",
                "provider": "Meta AI",
                "description": "NLLB-200 is Meta AI's state-of-the-art multilingual neural machine translation model with 1.3B parameters, supporting 200 languages across 24+ writing systems. This deployment focuses on African languages including Swahili, Yoruba, Hausa, Somali, Amharic, Tigrinya, and many others.",
                "supported_languages": [
                    "en", "sw", "yo", "ha", "so", "am", "ti", "ig", "zu", "xh", 
                    "sn", "rw", "om", "lg", "wo", "ts", "tn", "af", "fr", "ar"
                ],
                "supported_language_pairs": [
                    {"sourceLanguage": "en", "targetLanguage": "sw", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "sw", "targetLanguage": "en", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "en", "targetLanguage": "yo", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "yo", "targetLanguage": "en", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "en", "targetLanguage": "ha", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "ha", "targetLanguage": "en", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "en", "targetLanguage": "so", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "so", "targetLanguage": "en", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "en", "targetLanguage": "am", "sourceScriptCode": "Latn", "targetScriptCode": "Ethi"},
                    {"sourceLanguage": "am", "targetLanguage": "en", "sourceScriptCode": "Ethi", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "en", "targetLanguage": "ti", "sourceScriptCode": "Latn", "targetScriptCode": "Ethi"},
                    {"sourceLanguage": "ti", "targetLanguage": "en", "sourceScriptCode": "Ethi", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "en", "targetLanguage": "ig", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "ig", "targetLanguage": "en", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "sw", "targetLanguage": "yo", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "yo", "targetLanguage": "sw", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "sw", "targetLanguage": "ha", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "ha", "targetLanguage": "sw", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "fr", "targetLanguage": "sw", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "sw", "targetLanguage": "fr", "sourceScriptCode": "Latn", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "ar", "targetLanguage": "sw", "sourceScriptCode": "Arab", "targetScriptCode": "Latn"},
                    {"sourceLanguage": "sw", "targetLanguage": "ar", "sourceScriptCode": "Latn", "targetScriptCode": "Arab"}
                ]
            },
            {
                "service_id": "facebook/nllb-200-1.3B",
                "model_id": "facebook/nllb-200-1.3B",
                "triton_endpoint": "3.110.118.163:8000",
                "triton_model": "nmt",
                "provider": "Meta AI",
                "description": "NLLB-200 is Meta AI's state-of-the-art multilingual neural machine translation model with 1.3B parameters, supporting 200 languages across 24+ writing systems. This deployment focuses on African languages including Swahili, Yoruba, Hausa, Somali, Amharic, Tigrinya, and many others.",
                "supported_languages": [
                    "en", "sw", "yo", "ha", "so", "am", "ti", "ig", "zu", "xh", 
                    "sn", "rw", "om", "lg", "wo", "ts", "tn", "af", "fr", "ar"
                ]
            }
        ],
        "total_services": 5
    }


@inference_router.get(
    "/languages",
    response_model=Dict[str, Any],
    summary="Get supported languages",
    description="Get list of supported languages for a specific NMT model or service"
)
async def list_languages(
    model_id: Optional[str] = Query(None, description="Model ID to get languages for"),
    service_id: Optional[str] = Query(None, description="Service ID to get languages for")
) -> Dict[str, Any]:
    """List supported languages for a specific NMT model or service"""
    
    # Service ID to Model ID mapping
    SERVICE_TO_MODEL_MAP = {
        "ai4bharat/indictrans--gpu-t4": "ai4bharat/indictrans-v2-all-gpu--t4",
        "indictrans-v2-all": "ai4bharat/indictrans-v2-all-gpu--t4",
        "ai4bharat/indictrans-v2-all-gpu": "ai4bharat/indictrans-v2-all-gpu--t4",
        "translnew2": "facebook/nllb-200-1.3B",
        "facebook/nllb-200-1.3B": "facebook/nllb-200-1.3B"
    }
    
    # Determine model_id from service_id if provided
    if service_id:
        if service_id in SERVICE_TO_MODEL_MAP:
            model_id = SERVICE_TO_MODEL_MAP[service_id]
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_id}' not found. Available services: {', '.join(SERVICE_TO_MODEL_MAP.keys())}"
            )
    
    # Default to IndicTrans model if neither provided
    if not model_id:
        model_id = "ai4bharat/indictrans-v2-all-gpu--t4"
    
    # Hardcoded language data by model_id
    if model_id == "ai4bharat/indictrans-v2-all-gpu--t4":
        return {
            "model_id": "ai4bharat/indictrans-v2-all-gpu--t4",
            "provider": "AI4Bharat",
            "supported_languages": [
                "en", "gom", "gu", "sa", "te", "mr", "hi", "or", "mni", 
                "ml", "as", "doi", "sat", "ta", "sd", "bn", "ks", "kn", "ne"
            ],
            "language_details": [
                {"code": "en", "name": "English"},
                {"code": "gom", "name": "Goan Konkani"},
                {"code": "gu", "name": "Gujarati"},
                {"code": "sa", "name": "Sanskrit"},
                {"code": "te", "name": "Telugu"},
                {"code": "mr", "name": "Marathi"},
                {"code": "hi", "name": "Hindi"},
                {"code": "or", "name": "Odia"},
                {"code": "mni", "name": "Manipuri"},
                {"code": "ml", "name": "Malayalam"},
                {"code": "as", "name": "Assamese"},
                {"code": "doi", "name": "Dogri"},
                {"code": "sat", "name": "Santali"},
                {"code": "ta", "name": "Tamil"},
                {"code": "sd", "name": "Sindhi"},
                {"code": "bn", "name": "Bengali"},
                {"code": "ks", "name": "Kashmiri"},
                {"code": "kn", "name": "Kannada"},
                {"code": "ne", "name": "Nepali"}
            ],
            "total_languages": 19
        }
    elif model_id == "facebook/nllb-200-1.3B":
        return {
            "model_id": "facebook/nllb-200-1.3B",
            "provider": "Meta AI",
            "supported_languages": [
                "en", "sw", "yo", "ha", "so", "am", "ti", "ig", "zu", "xh", 
                "sn", "rw", "om", "lg", "wo", "ts", "tn", "af", "fr", "ar"
            ],
            "language_details": [
                {"code": "en", "name": "English"},
                {"code": "sw", "name": "Swahili"},
                {"code": "yo", "name": "Yoruba"},
                {"code": "ha", "name": "Hausa"},
                {"code": "so", "name": "Somali"},
                {"code": "am", "name": "Amharic"},
                {"code": "ti", "name": "Tigrinya"},
                {"code": "ig", "name": "Igbo"},
                {"code": "zu", "name": "Zulu"},
                {"code": "xh", "name": "Xhosa"},
                {"code": "sn", "name": "Shona"},
                {"code": "rw", "name": "Kinyarwanda"},
                {"code": "om", "name": "Oromo"},
                {"code": "lg", "name": "Ganda"},
                {"code": "wo", "name": "Wolof"},
                {"code": "ts", "name": "Tsonga"},
                {"code": "tn", "name": "Tswana"},
                {"code": "af", "name": "Afrikaans"},
                {"code": "fr", "name": "French"},
                {"code": "ar", "name": "Arabic"}
            ],
            "total_languages": 20,
            "supported_scripts": ["Latn", "Ethi", "Arab"]
        }
    else:
        raise HTTPException(
            status_code=404, 
            detail=f"Model '{model_id}' not found. Available models: ai4bharat/indictrans-v2-all-gpu--t4, facebook/nllb-200-1.3B"
        )
