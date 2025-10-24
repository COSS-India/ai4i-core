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
from services.tts_service import TTSService
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
from middleware.auth_provider import AuthProvider
from middleware.exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)

# Create router
inference_router = APIRouter(
    prefix="/api/v1/tts", 
    tags=["TTS Inference"]
    # Authentication disabled for development
)


async def get_tts_service(db: AsyncSession = Depends(get_db_session)) -> TTSService:
    """Dependency to get configured TTS service."""
    try:
        # Create repository
        repository = TTSRepository(db)
        
        # Create services
        audio_service = AudioService()
        text_service = TextService()
        
        # Create Triton client
        import os
        triton_url = os.getenv("TRITON_ENDPOINT", "http://localhost:8000")
        # Strip http:// or https:// scheme from URL (like ASR service)
        if triton_url.startswith(('http://', 'https://')):
            triton_url = triton_url.split('://', 1)[1]
        triton_api_key = os.getenv("TRITON_API_KEY")
        triton_client = TritonClient(triton_url, triton_api_key)
        
        # Create TTS service
        tts_service = TTSService(repository, audio_service, text_service, triton_client)
        
        return tts_service
        
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
        
        # Validate request
        await validate_request(request)
        
        # Log request
        logger.info(f"Processing TTS inference request with {len(request.input)} text inputs - user_id={user_id} api_key_id={api_key_id}")
        
        # Run inference with auth context
        response = await tts_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        
        # Log completion
        processing_time = time.time() - start_time
        logger.info(f"TTS inference completed in {processing_time:.2f}s")
        
        return response
        
    except ValueError as e:
        logger.warning(f"Validation error in TTS inference: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"TTS inference failed: {e}")
        
        # Return appropriate error based on exception type
        if "Triton" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="TTS service temporarily unavailable"
            )
        elif "text" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Text processing failed"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
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
