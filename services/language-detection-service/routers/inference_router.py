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
    """
    Dependency to construct LanguageDetectionService with Triton client resolved
    exclusively via Model Management (no environment variable fallback).

    ModelResolutionMiddleware (from ai4icore_model_management) must:
    - Extract config.serviceId from the request body
    - Resolve serviceId → triton_endpoint + model_name
    - Attach to request.state:
        - request.state.triton_endpoint
        - request.state.triton_model_name
        - request.state.service_id
    """
    repository = LanguageDetectionRepository(db)
    text_service = TextService()

    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.app.state, "triton_api_key", "")

    if not triton_endpoint:
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        
        if service_id:
            error_detail = (
                f"Model Management failed to resolve Triton endpoint for serviceId: {service_id}. "
                f"Please ensure the service is registered in Model Management database."
            )
            if model_mgmt_error:
                error_detail += f" Error: {model_mgmt_error}"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Request must include config.serviceId. "
                "Language Detection service requires Model Management database resolution."
            ),
        )

    # Get resolved model name from middleware (MUST be resolved by Model Management)
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Model Management failed to resolve Triton model name for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            ),
        )
    
    logger.info(
        "Using Triton endpoint=%s model_name=%s for serviceId=%s from Model Management",
        triton_endpoint,
        model_name,
        getattr(request.state, "service_id", "unknown"),
    )

    triton_client = TritonClient(triton_endpoint, triton_api_key or None)

    # LanguageDetectionService already supports dynamic endpoints internally if needed;
    # we pass the resolved client as the primary path.
    def get_triton_client_for_endpoint(endpoint: str) -> TritonClient:
        return TritonClient(triton_url=endpoint, api_key=triton_api_key or None)

    return LanguageDetectionService(
        repository,
        text_service,
        triton_client,
        get_triton_client_for_endpoint,
        resolved_model_name=model_name,
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
        
    except ValueError as exc:
        logger.warning("Validation error in Language Detection inference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        error_detail = str(exc)
        
        # Include model management context in error message
        if service_id and triton_endpoint:
            error_detail = (
                f"Language Detection inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                "Please verify the model is registered in Model Management and the Triton server is accessible."
            )
        elif service_id:
            error_detail = (
                f"Language Detection inference failed for serviceId '{service_id}': {error_detail}. "
                "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
            )
        else:
            error_detail = (
                f"Language Detection inference failed: {error_detail}. "
                "Please ensure config.serviceId is provided and the service is registered in Model Management."
            )
        
        logger.error("Language Detection inference failed: %s (serviceId=%s, endpoint=%s)", 
                    exc, service_id, triton_endpoint)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        ) from exc


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

