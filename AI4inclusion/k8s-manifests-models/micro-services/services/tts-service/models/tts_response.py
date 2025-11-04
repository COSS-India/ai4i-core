"""
TTS Response Models

Pydantic models for TTS inference responses.
"""

from typing import List, Optional
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
    
    def dict(self, **kwargs):
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)
