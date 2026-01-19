"""
TTS Request Models

Pydantic models for TTS inference requests, adapted from Dhruva-Platform-2 ULCA schemas.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class Gender(str, Enum):
    """Voice gender options for TTS."""
    MALE = "male"
    FEMALE = "female"


class AudioFormat(str, Enum):
    """Supported audio output formats."""
    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"
    PCM = "pcm"


class LanguageConfig(BaseModel):
    """Language configuration for TTS."""
    sourceLanguage: str = Field(..., description="Language code (e.g., 'en', 'hi', 'ta')")
    sourceScriptCode: Optional[str] = Field(None, description="Script code if applicable")
    
    @validator('sourceLanguage')
    def validate_language_code(cls, v):
        if not v or len(v) < 2 or len(v) > 3:
            raise ValueError('Language code must be 2-3 characters')
        return v


class TextInput(BaseModel):
    """Individual text input for TTS synthesis."""
    source: str = Field(..., description="Input text to synthesize")
    audioDuration: Optional[float] = Field(None, description="Desired audio duration in seconds (for precise timing)")
    
    @validator('source')
    def validate_source_text(cls, v):
        # Allow empty source and any length - will be validated in validation_utils with proper error codes
        if v is None:
            return ""
        # Strip whitespace but allow empty string to pass through for custom validation
        # Max length validation is done in validation_utils to return proper error codes
        return v.strip() if isinstance(v, str) else ""


class TTSInferenceConfig(BaseModel):
    """Configuration for TTS inference."""
    serviceId: str = Field(..., description="Identifier for TTS service/model")
    language: LanguageConfig = Field(..., description="Language configuration")
    gender: Gender = Field(..., description="Voice gender (male/female)")
    audioFormat: AudioFormat = Field(AudioFormat.WAV, description="Output audio format")
    samplingRate: Optional[int] = Field(22050, description="Target sample rate in Hz")
    encoding: str = Field("base64", description="Output encoding")
    
    @validator('samplingRate')
    def validate_sampling_rate(cls, v):
        if v is not None and (v < 8000 or v > 48000):
            raise ValueError('Sampling rate must be between 8000 and 48000 Hz')
        return v


class TTSInferenceRequest(BaseModel):
    """Main TTS inference request model."""
    input: List[TextInput] = Field(..., description="List of text inputs to synthesize")
    config: TTSInferenceConfig = Field(..., description="Configuration for inference")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")
    
    @validator('input')
    def validate_input_list(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one text input is required')
        return v
    
    def dict(self, **kwargs):
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)
