from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from models.voice_models import (
    VoiceMetadata,
    VoiceListResponse,
    VoiceGender,
    VoiceAge
)
from services.voice_service import VoiceService, VoiceNotFoundError

# Create router
router = APIRouter(prefix="/api/v1/tts", tags=["Voice Management"])


@router.get(
    "/voices",
    response_model=VoiceListResponse,
    summary="List available TTS voices",
    description="Get list of available voices with filtering options"
)
async def list_voices(
    language: Optional[str] = Query(None, description="Filter by language code"),
    gender: Optional[str] = Query(None, description="Filter by gender (male/female)"),
    age: Optional[str] = Query(None, description="Filter by age (young/adult/senior)"),
    is_active: Optional[bool] = Query(True, description="Filter by active status")
):
    """List available TTS voices with optional filtering."""
    try:
        # Create voice service
        voice_service = VoiceService()
        
        # Parse gender parameter
        parsed_gender = None
        if gender:
            try:
                parsed_gender = VoiceGender(gender.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid gender '{gender}'. Must be 'male' or 'female'"
                )
        
        # Parse age parameter
        parsed_age = None
        if age:
            try:
                parsed_age = VoiceAge(age.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid age '{age}'. Must be 'young', 'adult', or 'senior'"
                )
        
        # Get filtered voices
        voices = voice_service.list_voices(
            language=language,
            gender=parsed_gender,
            age=parsed_age,
            is_active=is_active
        )
        
        # Count total and filtered
        total_voices = len(voice_service.voices)
        filtered_voices = len(voices)
        
        return VoiceListResponse(
            voices=voices,
            total=total_voices,
            filtered=filtered_voices
        )
        
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/voices/{voice_id}",
    response_model=VoiceMetadata,
    summary="Get voice details by ID",
    description="Get detailed information about a specific voice"
)
async def get_voice_by_id(voice_id: str):
    """Get voice details by ID."""
    try:
        # Create voice service
        voice_service = VoiceService()
        
        # Get voice by ID
        voice = voice_service.get_voice_by_id(voice_id)
        
        if not voice:
            raise HTTPException(
                status_code=404,
                detail=f"Voice '{voice_id}' not found"
            )
        
        return voice
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/voices/language/{language}",
    response_model=List[VoiceMetadata],
    summary="List voices for a specific language",
    description="Get all voices that support the specified language"
)
async def get_voices_by_language(language: str):
    """Get all voices that support a specific language."""
    try:
        # Create voice service
        voice_service = VoiceService()
        
        # Get voices by language
        voices = voice_service.get_voices_by_language(language)
        
        return voices
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
