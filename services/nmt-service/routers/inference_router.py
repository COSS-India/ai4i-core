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
router = APIRouter(
    prefix="/api/v1/nmt",
    tags=["NMT Inference"],
    dependencies=[Depends(AuthProvider)]  # Add authentication dependency
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


@router.post(
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


@router.get(
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
                "model_id": "indictrans-v2-all",
                "language_pairs": [
                    {"source": "en", "target": "hi"},
                    {"source": "hi", "target": "en"},
                    {"source": "en", "target": "ta"},
                    {"source": "ta", "target": "en"},
                    {"source": "en", "target": "te"},
                    {"source": "te", "target": "en"},
                    {"source": "en", "target": "kn"},
                    {"source": "kn", "target": "en"},
                    {"source": "en", "target": "ml"},
                    {"source": "ml", "target": "en"},
                    {"source": "en", "target": "bn"},
                    {"source": "bn", "target": "en"},
                    {"source": "en", "target": "gu"},
                    {"source": "gu", "target": "en"},
                    {"source": "en", "target": "mr"},
                    {"source": "mr", "target": "en"},
                    {"source": "en", "target": "pa"},
                    {"source": "pa", "target": "en"},
                    {"source": "en", "target": "or"},
                    {"source": "or", "target": "en"},
                    {"source": "en", "target": "as"},
                    {"source": "as", "target": "en"},
                    {"source": "en", "target": "ur"},
                    {"source": "ur", "target": "en"}
                ],
                "description": "IndicTrans2 model supporting all Indian languages",
                "max_batch_size": 90,
                "supported_scripts": ["Deva", "Arab", "Taml", "Telu", "Knda", "Mlym", "Beng", "Gujr", "Guru", "Orya"]
            }
        ],
        "total_models": 1,
        "supported_languages": [
            "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", 
            "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", 
            "mai", "brx", "mni"
        ]
    }
