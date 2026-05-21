"""Audio Language Detection service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AudioInput(BaseModel):
    """Input for audio-based language detection task."""

    audio_content: Optional[str] = Field(None, description="Base64 encoded audio data")
    audio_uri: Optional[str] = Field(None, description="HTTP URL to audio file")


class AudioLanguageDetectionConfig(BaseModel):
    """Configuration for audio language detection inference."""

    service_id: str = Field(..., description="Service ID (required)")
    return_all_scores: Optional[bool] = Field(False, description="Return scores for all languages")


class AudioLanguageDetectionInferenceRequest(BaseModel):
    """Request for audio language detection inference."""

    audio: List[AudioInput] = Field(
        ..., min_items=1, description="Audio inputs for language detection"
    )
    config: AudioLanguageDetectionConfig = Field(
        ..., description="Audio language detection configuration"
    )


class LanguagePrediction(BaseModel):
    """Language prediction with confidence score."""

    language_code: str = Field(..., description="ISO 639-1 language code (e.g., 'en')")
    language: str = Field(..., description="Language name (e.g., 'English')")
    confidence: float = Field(..., description="Confidence score (0-1)")


class AudioLanguageDetectionOutput(BaseModel):
    """Output from audio language detection inference."""

    predicted_language: LanguagePrediction = Field(..., description="Primary detected language")
    all_scores: Optional[List[LanguagePrediction]] = Field(
        None, description="All language predictions if requested"
    )
    duration_ms: Optional[float] = Field(None, description="Audio duration in milliseconds")


class AudioLanguageDetectionInferenceResponse(BaseModel):
    """Response from audio language detection inference."""

    output: List[AudioLanguageDetectionOutput] = Field(
        ..., description="Audio language detection results"
    )

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
