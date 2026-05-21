"""TTS (Text-to-Speech) service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TextInput(BaseModel):
    """Input for TTS task."""

    source: str = Field(..., description="Text to synthesize to speech")


class TTSLanguageConfig(BaseModel):
    """Language configuration for TTS."""

    target_language: str = Field(..., description="Target language code for speech")


class TTSConfig(BaseModel):
    """Configuration for TTS inference."""

    service_id: Optional[str] = Field(None, description="Service ID (optional, resolved by SMR)")
    language: TTSLanguageConfig = Field(..., description="Language configuration")
    voice_id: Optional[str] = Field(None, description="Voice ID for synthesis")
    sample_rate: Optional[int] = Field(22050, description="Output sample rate in Hz")
    duration_seconds: Optional[float] = Field(None, description="Desired audio duration")


class TTSInferenceRequest(BaseModel):
    """Request for TTS inference."""

    input: List[TextInput] = Field(..., min_items=1, description="Text inputs to synthesize")
    config: TTSConfig = Field(..., description="TTS configuration")


class AudioMetadata(BaseModel):
    """Metadata about synthesized audio."""

    duration_ms: float = Field(..., description="Duration of audio in milliseconds")
    sample_rate: int = Field(..., description="Sample rate in Hz")
    num_channels: int = Field(1, description="Number of audio channels")


class TTSOutput(BaseModel):
    """Output from TTS inference."""

    audio_content: str = Field(..., description="Base64 encoded audio data")
    audio_format: str = Field("wav", description="Audio format (wav, mp3, ogg, etc.)")
    metadata: AudioMetadata = Field(..., description="Audio metadata")


class TTSInferenceResponse(BaseModel):
    """Response from TTS inference."""

    output: List[TTSOutput] = Field(..., description="Synthesized audio results")
    smr_response: Optional[Dict[str, Any]] = Field(None, description="Smart Model Router metadata")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
