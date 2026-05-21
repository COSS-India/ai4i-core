"""Language Diarization service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AudioInput(BaseModel):
    """Input for audio-based language diarization task."""

    audio_content: Optional[str] = Field(None, description="Base64 encoded audio data")
    audio_uri: Optional[str] = Field(None, description="HTTP URL to audio file")


class LanguageDiarizationConfig(BaseModel):
    """Configuration for language diarization inference."""

    service_id: str = Field(..., description="Service ID (required)")


class LanguageDiarizationInferenceRequest(BaseModel):
    """Request for language diarization inference."""

    audio: List[AudioInput] = Field(..., min_items=1, description="Audio inputs for language diarization")
    config: LanguageDiarizationConfig = Field(..., description="Language diarization configuration")


class DiarizationSegment(BaseModel):
    """Language segment with timeline."""

    start_time_ms: float = Field(..., description="Segment start time in milliseconds")
    end_time_ms: float = Field(..., description="Segment end time in milliseconds")
    language: str = Field(..., description="Language code for this segment")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")


class LanguageDiarizationOutput(BaseModel):
    """Output from language diarization inference."""

    segments: List[DiarizationSegment] = Field(..., description="Language segments with timing")
    duration_ms: float = Field(..., description="Total audio duration in milliseconds")


class LanguageDiarizationInferenceResponse(BaseModel):
    """Response from language diarization inference."""

    output: List[LanguageDiarizationOutput] = Field(..., description="Language diarization results")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
