import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request

from sqlalchemy.ext.asyncio import AsyncSession

from models.language_detection_request import LanguageDetectionInferenceRequest
from models.language_detection_response import LanguageDetectionInferenceResponse
from repositories.language_detection_repository import LanguageDetectionRepository, get_db_session
from services.language_detection_service import LanguageDetectionService
from services.text_service import TextService
from utils.triton_client import TritonClient
from middleware.auth_provider import AuthProvider

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/language-detection",
    tags=["Language Detection"],
    dependencies=[Depends(AuthProvider)]
)


async def get_language_detection_service(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> LanguageDetectionService:
    repository = LanguageDetectionRepository(db)
    text_service = TextService()
    
    default_triton_client = TritonClient(
        triton_url=request.app.state.triton_endpoint,
        api_key=request.app.state.triton_api_key
    )
    
    def get_triton_client_for_endpoint(endpoint: str) -> TritonClient:
        return TritonClient(
            triton_url=endpoint,
            api_key=request.app.state.triton_api_key
        )
    
    return LanguageDetectionService(
        repository,
        text_service,
        default_triton_client,
        get_triton_client_for_endpoint
    )


@inference_router.post(
    "/inference",
    response_model=LanguageDetectionInferenceResponse,
    summary="Detect language of text",
    description="Detect the language and script of input text using IndicLID model"
)
async def run_inference(
    request_body: LanguageDetectionInferenceRequest,
    http_request: Request,
    language_detection_service: LanguageDetectionService = Depends(get_language_detection_service)
) -> LanguageDetectionInferenceResponse:
    try:
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_name = getattr(http_request.state, 'api_key_name', None)
        
        logger.info(f"Processing language detection request for user_id={user_id}")
        
        response = await language_detection_service.run_inference(
            request=request_body,
            api_key_name=api_key_name,
            user_id=user_id
        )
        
        logger.info("Language detection completed successfully")
        return response
        
    except Exception as e:
        logger.error(f"Language detection failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e}"
        )


@inference_router.get(
    "/languages",
    response_model=Dict[str, Any],
    summary="Get supported languages",
    description="Get list of supported languages and scripts for language detection"
)
async def list_languages() -> Dict[str, Any]:
    return {
        "languages": [
            {"code": "as", "name": "Assamese", "scripts": ["Beng", "Latn"]},
            {"code": "bn", "name": "Bengali", "scripts": ["Beng", "Latn"]},
            {"code": "brx", "name": "Bodo", "scripts": ["Deva", "Latn"]},
            {"code": "doi", "name": "Dogri", "scripts": ["Deva", "Latn"]},
            {"code": "en", "name": "English", "scripts": ["Latn"]},
            {"code": "gu", "name": "Gujarati", "scripts": ["Gujr", "Latn"]},
            {"code": "hi", "name": "Hindi", "scripts": ["Deva", "Latn"]},
            {"code": "kn", "name": "Kannada", "scripts": ["Knda", "Latn"]},
            {"code": "ks", "name": "Kashmiri", "scripts": ["Arab", "Deva", "Latn"]},
            {"code": "kok", "name": "Konkani", "scripts": ["Deva", "Latn"]},
            {"code": "mai", "name": "Maithili", "scripts": ["Deva", "Latn"]},
            {"code": "ml", "name": "Malayalam", "scripts": ["Mlym", "Latn"]},
            {"code": "mni", "name": "Manipuri", "scripts": ["Beng", "Mtei", "Latn"]},
            {"code": "mr", "name": "Marathi", "scripts": ["Deva", "Latn"]},
            {"code": "ne", "name": "Nepali", "scripts": ["Deva", "Latn"]},
            {"code": "or", "name": "Odia", "scripts": ["Orya", "Latn"]},
            {"code": "pa", "name": "Punjabi", "scripts": ["Guru", "Latn"]},
            {"code": "sa", "name": "Sanskrit", "scripts": ["Deva", "Latn"]},
            {"code": "sat", "name": "Santali", "scripts": ["Olck"]},
            {"code": "sd", "name": "Sindhi", "scripts": ["Arab", "Latn"]},
            {"code": "ta", "name": "Tamil", "scripts": ["Taml", "Latn"]},
            {"code": "te", "name": "Telugu", "scripts": ["Telu", "Latn"]},
            {"code": "ur", "name": "Urdu", "scripts": ["Arab", "Latn"]},
            {"code": "other", "name": "Other", "scripts": ["Latn"]}
        ],
        "total_languages": 23,
        "model": "ai4bharat/indiclid"
    }


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available language detection models",
    description="Get list of supported language detection models"
)
async def list_models() -> Dict[str, Any]:
    return {
        "models": [
            {
                "model_id": "ai4bharat/indiclid",
                "provider": "AI4Bharat",
                "supported_languages": 23,
                "description": "IndicLID model for identifying Indian language text and scripts",
                "max_batch_size": 100
            }
        ],
        "total_models": 1
    }

