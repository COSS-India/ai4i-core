"""
TTS Response Models

Pydantic models for TTS inference responses.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from models.tts_request import LanguageConfig, AudioFormat


class AudioOutput(BaseModel):
    """Audio output containing synthesized speech."""
    audioContent: str = Field(..., description="Base64-encoded audio data")
    audioUri: Optional[str] = Field(None, description="URL to audio file (if stored externally)")
    
    def dict(self, **kwargs):
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class AudioConfig(BaseModel):
    """Audio configuration metadata for the response."""
    language: LanguageConfig = Field(..., description="Language configuration")
    audioFormat: AudioFormat = Field(..., description="Format of output audio")
    encoding: str = Field("base64", description="Encoding type")
    samplingRate: int = Field(..., description="Sample rate in Hz")
    audioDuration: Optional[float] = Field(None, description="Actual audio duration in seconds")


class TTSInferenceResponse(BaseModel):
    """Main TTS inference response model."""
    audio: List[AudioOutput] = Field(..., description="List of generated audio outputs (one per text input)")
    config: Optional[AudioConfig] = Field(None, description="Response configuration metadata")
    # SMR response if SMR was used to resolve serviceId or policies
    smr_response: Optional[Dict[str, Any]] = Field(
        None,
        description="SMR response metadata when Smart Model Routing is used",
    )
    
    def dict(self, **kwargs):
        """
        Override dict() to exclude None values by default.
        But allow exclude_none=False to be passed explicitly to include None values (e.g., for smr_response).
        """
        # If exclude_none is explicitly set, respect it
        if "exclude_none" in kwargs:
            return super().dict(**kwargs)
        # Default behavior: exclude None values
        return super().dict(exclude_none=True, **kwargs)
