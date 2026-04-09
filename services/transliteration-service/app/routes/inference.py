"""Transliteration inference endpoint."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks
from ai4icore_constants.error_messages import (
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_MESSAGE,
)

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_transliteration_service
from app.schemas.inference import (
    TransliterationInferenceRequest,
    TransliterationInferenceResponse,
)
from app.services.transliteration_service import TransliterationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/transliteration",
    tags=["Transliteration Inference"],
    dependencies=[Depends(AuthProvider)],
)


async def enforce_transliteration_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="transliteration",
        service_unavailable_code=SERVICE_UNAVAILABLE,
        service_inactive_message="Transliteration service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect Transliteration service availability. Please contact your administrator",
        timeout_message=SERVICE_UNAVAILABLE_MESSAGE,
        generic_unavailable_message=SERVICE_UNAVAILABLE_MESSAGE,
    )


router.dependencies.append(Depends(enforce_transliteration_checks))


@router.post("/inference", response_model=TransliterationInferenceResponse)
async def run_inference(
    request_body: TransliterationInferenceRequest,
    http_request: Request,
    transliteration_service: TransliterationService = Depends(get_transliteration_service),
) -> TransliterationInferenceResponse:
    """Run transliteration inference for a batch of text inputs."""
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    return await transliteration_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
    )


@router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available transliteration models",
    description="Get list of supported transliteration models and language pairs",
)
async def list_models() -> Dict[str, Any]:
    """List available transliteration models and language pairs."""
    return {
        "models": [
            {
                "model_id": "ai4bharat/indicxlit",
                "provider": "AI4Bharat",
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                    "mai", "brx", "mni", "sat", "gom",
                ],
                "description": "IndicXlit model supporting transliteration for 20+ Indic languages",
                "max_batch_size": 100,
                "supports_sentence_level": True,
                "supports_word_level": True,
                "supports_top_k": True,
            }
        ],
        "total_models": 1,
    }


@router.get(
    "/services",
    response_model=Dict[str, Any],
    summary="List available transliteration services",
    description="Get list of supported transliteration services with their Triton endpoints",
)
async def list_services() -> Dict[str, Any]:
    """List available transliteration services and their endpoints."""
    return {
        "services": [
            {
                "service_id": "ai4bharat/indicxlit",
                "model_id": "ai4bharat/indicxlit",
                "triton_endpoint": "",
                "triton_model": "transliteration",
                "provider": "AI4Bharat",
                "description": "IndicXlit model supporting transliteration for 20+ Indic languages",
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                    "mai", "brx", "mni", "sat", "gom",
                ],
            },
            {
                "service_id": "indicxlit",
                "model_id": "ai4bharat/indicxlit",
                "triton_endpoint": "",
                "triton_model": "transliteration",
                "provider": "AI4Bharat",
                "description": "IndicXlit model supporting transliteration for 20+ Indic languages (alias)",
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                    "mai", "brx", "mni", "sat", "gom",
                ],
            },
        ],
        "total_services": 2,
    }


@router.get(
    "/languages",
    response_model=Dict[str, Any],
    summary="Get supported languages",
    description="Get list of supported languages for a specific transliteration model or service",
)
async def list_languages(
    model_id: Optional[str] = Query(None, description="Model ID to get languages for"),
    service_id: Optional[str] = Query(None, description="Service ID to get languages for"),
) -> Dict[str, Any]:
    """List supported languages for a specific transliteration model or service."""
    SERVICE_TO_MODEL_MAP = {
        "ai4bharat/indicxlit": "ai4bharat/indicxlit",
        "indicxlit": "ai4bharat/indicxlit",
    }

    if service_id:
        if service_id in SERVICE_TO_MODEL_MAP:
            model_id = SERVICE_TO_MODEL_MAP[service_id]
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_id}' not found. Available services: {', '.join(SERVICE_TO_MODEL_MAP.keys())}",
            )

    if not model_id:
        model_id = "ai4bharat/indicxlit"

    if model_id == "ai4bharat/indicxlit":
        return {
            "model_id": "ai4bharat/indicxlit",
            "provider": "AI4Bharat",
            "supported_languages": [
                "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
                "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
                "mai", "brx", "mni", "sat", "gom",
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
                {"code": "gom", "name": "Goan Konkani"},
            ],
            "total_languages": 24,
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found. Available models: ai4bharat/indicxlit",
        )
