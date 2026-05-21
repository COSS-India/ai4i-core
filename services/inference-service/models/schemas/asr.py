"""ASR (Automatic Speech Recognition) service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AudioInput(BaseModel):
    """Input for audio-based ASR task."""

    audio_content: Optional[str] = Field(None, description="Base64 encoded audio data")
    audio_uri: Optional[str] = Field(None, description="HTTP URL to audio file")
    sample_rate: Optional[int] = Field(None, description="Audio sample rate in Hz")


class ASRLanguageConfig(BaseModel):
    """Language configuration for ASR."""

    source_language: str = Field(..., description="Language code (e.g., 'en')")
    source_script_code: Optional[str] = Field(None, description="Script code (e.g., 'Latn')")


class ASRConfig(BaseModel):
    """Configuration for ASR inference."""

    service_id: Optional[str] = Field(None, description="Service ID (optional, resolved by SMR)")
    language: ASRLanguageConfig = Field(..., description="Language configuration")
    sample_rate: Optional[int] = Field(None, description="Audio sample rate in Hz")
    audio_channels: Optional[int] = Field(1, description="Number of audio channels")
    n_best: Optional[int] = Field(1, description="Return top N best transcriptions")
    enable_punctuation: Optional[bool] = Field(False, description="Enable punctuation in output")


class ASRInferenceRequest(BaseModel):
    """Request for ASR inference."""

    audio: List[AudioInput] = Field(..., min_items=1, description="Audio inputs to transcribe")
    config: ASRConfig = Field(..., description="ASR configuration")


class TranscriptionAlternative(BaseModel):
    """Alternative transcription with confidence score."""

    transcript: str = Field(..., description="Transcribed text")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")


class TranscriptionOutput(BaseModel):
    """Output from ASR inference."""

    transcript: str = Field(..., description="Primary transcription")
    alternatives: Optional[List[TranscriptionAlternative]] = Field(
        None, description="N-best alternatives if requested"
    )
    duration_ms: Optional[float] = Field(None, description="Duration of audio in milliseconds")


class ASRInferenceResponse(BaseModel):
    """Response from ASR inference."""

    output: List[TranscriptionOutput] = Field(..., description="Transcription results")
    smr_response: Optional[Dict[str, Any]] = Field(None, description="Smart Model Router metadata")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
