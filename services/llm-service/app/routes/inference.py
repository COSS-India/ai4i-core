"""LLM inference endpoint."""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import AuthProvider
from app.dependencies.llm_tenant import enforce_llm_checks
from app.dependencies.services import get_llm_service
from app.schemas.inference import LLMInferenceRequest, LLMInferenceResponse
from app.services.llm_service import LLMService
from utils.llm_pay_per_use import _llm_ppu_check, _llm_ppu_record, raise_if_ppu_denied

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/llm",
    tags=["LLM Inference"],
    dependencies=[Depends(AuthProvider)],
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

    input_texts = [item.source for item in request_body.input]
    allowed = await _llm_ppu_check(http_request, input_texts)
    raise_if_ppu_denied(allowed)

    result = await llm_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
        http_request=http_request,
    )
    asyncio.create_task(_llm_ppu_record(http_request, result.raw_response, input_texts))
    return result


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
