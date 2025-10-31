"""
Inference Router
FastAPI router for LLM inference endpoints
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.llm_request import LLMInferenceRequest
from models.llm_response import LLMInferenceResponse
from repositories.llm_repository import LLMRepository
from services.llm_service import LLMService
from utils.triton_client import TritonClient

logger = logging.getLogger(__name__)

# Create router
inference_router = APIRouter(
    prefix="/api/v1/llm",
    tags=["LLM Inference"],
    # dependencies=[Depends(AuthProvider)]  # Commented out for testing
)


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session"""
    return request.app.state.db_session_factory()


async def get_llm_service(request: Request, db: AsyncSession = Depends(get_db_session)) -> LLMService:
    """Dependency to get configured LLM service"""
    repository = LLMRepository(db)
    triton_client = TritonClient(
        triton_url=request.app.state.triton_endpoint,
        api_key=request.app.state.triton_api_key
    )
    return LLMService(repository, triton_client)


@inference_router.post(
    "/inference",
    response_model=LLMInferenceResponse,
    summary="Perform LLM inference",
    description="Process text using LLM for language processing (translation, generation, etc.)"
)
async def run_inference(
    request: LLMInferenceRequest,
    http_request: Request,
    llm_service: LLMService = Depends(get_llm_service)
) -> LLMInferenceResponse:
    """Run LLM inference on the given request"""
    try:
        # Extract auth context from request.state
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_id = getattr(http_request.state, 'api_key_id', None)
        session_id = getattr(http_request.state, 'session_id', None)
        
        # Log incoming request
        logger.info(f"Processing LLM inference request with {len(request.input)} texts")
        
        # Run inference
        response = await llm_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        
        logger.info(f"LLM inference completed successfully")
        return response
        
    except Exception as e:
        logger.error(f"LLM inference failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available LLM models",
    description="Get list of supported LLM models"
)
async def list_models() -> Dict[str, Any]:
    """List available LLM models"""
    return {
        "models": [
            {
                "model_id": "llm",
                "provider": "AI4Bharat",
                "description": "LLM model for text processing, translation, and generation",
                "max_batch_size": 100,
                "supported_languages": ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or", "as", "ur"]
            }
        ],
        "total_models": 1
    }

