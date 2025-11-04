"""
Inference Router
FastAPI router for NMT inference endpoints
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
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


async def get_nmt_service(request: Request, db: AsyncSession = Depends(get_db_session)) -> NMTService:
    """Dependency to get configured NMT service"""
    repository = NMTRepository(db)
    text_service = TextService()
    triton_client = TritonClient(
        triton_url=request.app.state.triton_endpoint,
        api_key=request.app.state.triton_api_key
    )
    return NMTService(repository, text_service, triton_client)


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
        logger.error(f"NMT inference failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
            }
        ],
        "total_models": 1
    }


@inference_router.get(
    "/languages",
    response_model=Dict[str, Any],
    summary="Get supported languages",
    description="Get list of supported languages for a specific NMT model"
)
async def list_languages(model_id: str = "ai4bharat/indictrans-v2-all-gpu--t4") -> Dict[str, Any]:
    """List supported languages for a specific NMT model"""
    
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
    else:
        raise HTTPException(
            status_code=404, 
            detail=f"Model '{model_id}' not found. Available models: ai4bharat/indictrans-v2-all-gpu--t4"
        )
