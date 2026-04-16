"""LLM inference endpoint."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_llm_service
from app.schemas.inference import LLMInferenceRequest, LLMInferenceResponse
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/llm",
    tags=["LLM Inference"],
    dependencies=[Depends(AuthProvider)],
)


async def enforce_llm_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="llm",
        service_unavailable_code="SERVICE_UNAVAILABLE",
        service_inactive_message="LLM service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect LLM service availability. Please contact your administrator",
        timeout_message="LLM service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="LLM service is temporarily unavailable. Please try again in a few minutes.",
    )


router.dependencies.append(Depends(enforce_llm_checks))


@router.post("/inference", response_model=LLMInferenceResponse)
async def run_inference(
    request_body: LLMInferenceRequest,
    http_request: Request,
    llm_service: LLMService = Depends(get_llm_service),
) -> LLMInferenceResponse:
    """Run LLM inference for a batch of text inputs."""
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    return await llm_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
    )


@router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available LLM models",
    description="Get list of supported LLM models",
)
async def list_models() -> Dict[str, Any]:
    """List available LLM models."""
    return {
        "models": [
            {
                "model_id": "llm",
                "provider": "AI4Bharat",
                "description": "LLM model for text processing, translation, and generation",
                "max_batch_size": 100,
                "supported_languages": [
                    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or", "as", "ur",
                ],
            }
        ],
        "total_models": 1,
    }
