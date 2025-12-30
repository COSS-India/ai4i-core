"""
FastAPI router for TTS inference endpoints.
"""

import logging
import time
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.tts_request import TTSInferenceRequest
from models.tts_response import TTSInferenceResponse
from repositories.tts_repository import TTSRepository, get_db_session
from services.tts_service import TTSService, TritonInferenceError
from services.audio_service import AudioService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.validation_utils import (
    validate_language_code,
    validate_service_id,
    validate_gender,
    validate_audio_format,
    validate_sample_rate,
    validate_text_input,
    validate_audio_duration
)
from middleware.exceptions import AuthenticationError, AuthorizationError
from ai4icore_model_management import ModelManagementClient, extract_auth_headers

logger = logging.getLogger(__name__)

# Create router
# Authentication is handled by Kong + Auth Service, no need for AuthProvider here
inference_router = APIRouter(
    prefix="/api/v1/tts", 
    tags=["TTS Inference"]
)


async def get_tts_service(request: Request, db: AsyncSession = Depends(get_db_session)) -> TTSService:
    """Dependency to get configured TTS service."""
    try:
        # Create repository
        repository = TTSRepository(db)
        
        # Create services
        audio_service = AudioService()
        text_service = TextService()
        
        # Factory function to create Triton clients for different endpoints
        def get_triton_client_for_endpoint(endpoint: str) -> TritonClient:
            """Create Triton client for specific endpoint"""
            import os
            # Get default API key from app state (can be overridden per-service from model management)
            default_api_key = getattr(request.app.state, "triton_api_key", os.getenv("TRITON_API_KEY", ""))
            return TritonClient(triton_url=endpoint, api_key=default_api_key)
        
        # Get model management client from app state (REQUIRED)
        model_management_client = getattr(request.app.state, "model_management_client", None)
        if model_management_client is None:
            logger.error("Model management client not available. Service cannot start without it.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Model management service is not available. The TTS service requires model management to operate."
            )
        
        redis_client = getattr(request.app.state, "redis_client", None)
        cache_ttl = getattr(request.app.state, "tts_endpoint_cache_ttl", 300)
        
        # Create TTS service
        tts_service = TTSService(
            repository=repository,
            audio_service=audio_service,
            text_service=text_service,
            get_triton_client_func=get_triton_client_for_endpoint,
            model_management_client=model_management_client,
            redis_client=redis_client,
            cache_ttl_seconds=cache_ttl
        )
        
        return tts_service
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create TTS service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize TTS service"
        )


@inference_router.post(
    "/inference",
    response_model=TTSInferenceResponse,
    summary="Perform batch TTS inference",
    description="Convert text to speech for one or more text inputs"
)
async def run_inference(
    request: TTSInferenceRequest,
    http_request: Request,
    tts_service: TTSService = Depends(get_tts_service)
) -> TTSInferenceResponse:
    """Run TTS inference on text inputs."""
    start_time = time.time()
    request_id = None
    
    try:
        # Extract auth context from request.state
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_id = getattr(http_request.state, 'api_key_id', None)
        session_id = getattr(http_request.state, 'session_id', None)
        
        # Extract auth headers for model management service calls
        auth_headers = extract_auth_headers(http_request)
        
        # Validate request
        await validate_request(request)
        
        # Log request
        logger.info(f"Processing TTS inference request with {len(request.input)} text inputs - user_id={user_id} api_key_id={api_key_id}")
        
        response = await tts_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
            auth_headers=auth_headers
        )
        
        # Log completion
        processing_time = time.time() - start_time
        logger.info(f"TTS inference completed in {processing_time:.2f}s")
        
        return response
        
    except ValueError as e:
        # Handle service ID not found errors from model management service
        error_msg = str(e)
        logger.warning(f"Validation error in TTS inference: {e}")
        
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service ID '{request.config.serviceId}' not found. Please verify the service ID is correct and registered in the model management service."
            )
        elif "endpoint" in error_msg.lower() and ("not configured" in error_msg.lower() or "no endpoint" in error_msg.lower()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service ID '{request.config.serviceId}' has no endpoint configured. Please configure the endpoint in the model management service."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    except TritonInferenceError as e:
        error_msg = str(e)
        logger.error(f"TTS Triton inference failed: {e}", exc_info=True)
        
        if "not found" in error_msg.lower() or "404" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Triton model not found: {error_msg}"
            )
        elif "connect" in error_msg.lower() or "connection" in error_msg.lower() or "refused" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Cannot connect to Triton server: {error_msg}"
            )
        elif "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"Triton inference request timed out: {error_msg}"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"TTS service temporarily unavailable: {error_msg}"
            )
    except Exception as e:
        logger.error(f"TTS inference failed: {e}", exc_info=True)
        error_msg = str(e)
        
        # Service ID not found errors
        if "service" in error_msg.lower() and ("not found" in error_msg.lower() or "does not exist" in error_msg.lower()):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service ID '{request.config.serviceId}' not found. Please verify the service ID is correct and registered."
            )
        
        # Triton endpoint errors
        if "Triton" in error_msg or "triton" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"TTS service temporarily unavailable: {error_msg}"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {error_msg}"
        )


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available TTS models",
    description="Get list of supported TTS models, languages, and voices"
)
async def list_models() -> Dict[str, Any]:
    """List available TTS models."""
    return {
        "models": [
            {
                "model_id": "indic-tts-coqui-dravidian",
                "languages": ["kn", "ml", "ta", "te"],
                "voices": ["male", "female"],
                "description": "Dravidian language TTS model"
            },
            {
                "model_id": "indic-tts-coqui-indo_aryan",
                "languages": ["hi", "bn", "gu", "mr", "pa"],
                "voices": ["male", "female"],
                "description": "Indo-Aryan language TTS model"
            },
            {
                "model_id": "indic-tts-coqui-misc",
                "languages": ["en", "brx", "mni"],
                "voices": ["male", "female"],
                "description": "Miscellaneous language TTS model"
            }
        ],
        "supported_languages": [
            "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
            "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai",
            "brx", "mni"
        ],
        "supported_voices": ["male", "female"],
        "supported_formats": ["wav", "mp3", "ogg", "pcm"],
        "supported_sample_rates": [8000, 16000, 22050, 44100, 48000]
    }


async def validate_request(request: TTSInferenceRequest) -> None:
    """Validate TTS inference request."""
    try:
        # Validate service ID
        validate_service_id(request.config.serviceId)
        
        # Validate language code
        validate_language_code(request.config.language.sourceLanguage)
        
        # Validate gender
        validate_gender(request.config.gender.value)
        
        # Validate audio format
        validate_audio_format(request.config.audioFormat.value)
        
        # Validate sample rate
        if request.config.samplingRate:
            validate_sample_rate(request.config.samplingRate)
        
        # Validate text inputs
        for text_input in request.input:
            validate_text_input(text_input.source)
            
            # Validate audio duration if specified
            if text_input.audioDuration:
                validate_audio_duration(text_input.audioDuration)
        
    except Exception as e:
        logger.warning(f"Request validation failed: {e}")
        raise ValueError(f"Invalid request: {e}")
