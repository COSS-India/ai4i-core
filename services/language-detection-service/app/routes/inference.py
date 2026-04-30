"""Language Detection inference endpoint."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_language_detection_service
from app.schemas.inference import (
    LanguageDetectionInferenceRequest,
    LanguageDetectionInferenceResponse,
)
from app.services.language_detection_service import LanguageDetectionService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/language-detection",
    tags=["Language Detection"],
    dependencies=[Depends(AuthProvider)],
)


async def enforce_language_detection_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="language_detection",
        service_unavailable_code="SERVICE_UNAVAILABLE",
        service_inactive_message="Language Detection service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect Language Detection service availability. Please contact your administrator",
        timeout_message="Language Detection service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="Language Detection service is temporarily unavailable. Please try again in a few minutes.",
    )


router.dependencies.append(Depends(enforce_language_detection_checks))


@router.post("/inference", response_model=LanguageDetectionInferenceResponse)
async def run_inference(
    request_body: LanguageDetectionInferenceRequest,
    http_request: Request,
    language_detection_service: LanguageDetectionService = Depends(get_language_detection_service),
) -> LanguageDetectionInferenceResponse:
    """Run language detection inference on the given request."""
    user_id = getattr(http_request.state, "user_id", None)
    api_key_name = getattr(http_request.state, "api_key_name", None)

    return await language_detection_service.run_inference(
        request=request_body,
        api_key_name=api_key_name,
        user_id=user_id,
    )


@router.get(
    "/languages",
    response_model=Dict[str, Any],
    summary="Get supported languages",
    description="Get list of supported languages and scripts for language detection",
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
            {"code": "other", "name": "Other", "scripts": ["Latn"]},
        ],
        "total_languages": 23,
        "model": "ai4bharat/indiclid",
    }


@router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available language detection models",
    description="Get list of supported language detection models",
)
async def list_models() -> Dict[str, Any]:
    return {
        "models": [
            {
                "model_id": "ai4bharat/indiclid",
                "provider": "AI4Bharat",
                "supported_languages": 23,
                "description": "IndicLID model for identifying Indian language text and scripts",
                "max_batch_size": 100,
            }
        ],
        "total_models": 1,
    }
