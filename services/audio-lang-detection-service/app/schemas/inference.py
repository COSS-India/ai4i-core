"""
Audio Language Detection Request & Response Models

Pydantic models for audio language detection inference requests and responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


# ── Request models ──


class ControlConfig(BaseModel):
    """Control configuration for audio language detection."""

    dataTracking: Optional[bool] = Field(
        True, description="Whether to enable data tracking"
    )


class AudioLangDetectionConfig(BaseModel):
    """Configuration for audio language detection inference."""

    serviceId: str = Field(
        ...,
        description="Identifier for audio language detection service/model",
    )


class AudioInput(BaseModel):
    """Audio input specification."""

    audioContent: Optional[str] = Field(
        None, description="Base64 encoded audio content"
    )
    audioUri: Optional[HttpUrl] = Field(
        None, description="URL from which the audio can be downloaded"
    )

    @model_validator(mode="after")
    def validate_audio_input(self) -> "AudioInput":
        """Ensure at least one of audioContent or audioUri is provided."""
        if not self.audioContent and not self.audioUri:
            raise ValueError(
                "At least one of audioContent or audioUri must be provided"
            )
        return self


class AudioLangDetectionInferenceRequest(BaseModel):
    """Main audio language detection inference request model."""

    controlConfig: Optional[ControlConfig] = Field(
        None, description="Control configuration parameters"
    )
    config: AudioLangDetectionConfig = Field(
        ..., description="Configuration for audio language detection inference"
    )
    audio: List[AudioInput] = Field(
        ..., description="List of audio inputs to process", min_items=1
    )

    @model_validator(mode="after")
    def validate_audio_list(self) -> "AudioLangDetectionInferenceRequest":
        """Ensure at least one audio input is provided."""
        if not self.audio:
            raise ValueError("At least one audio input is required")
        return self

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


# ── Response models ──


class AllScores(BaseModel):
    """All scores from language detection model."""

    predicted_language: str = Field(..., description="Predicted language code with name")
    confidence: float = Field(..., description="Confidence score")
    top_scores: List[float] = Field(..., description="Top confidence scores")

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class AudioLangDetectionOutput(BaseModel):
    """Output for a single audio input."""

    language_code: str = Field(..., description="Detected language code with name (e.g., 'ta: Tamil')")
    confidence: float = Field(..., description="Confidence score for the detected language")
    all_scores: AllScores = Field(..., description="All scores from the detection model")

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class AudioLangDetectionResponseConfig(BaseModel):
    """Response configuration metadata."""

    serviceId: str = Field(..., description="Service identifier")

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class AudioLangDetectionInferenceResponse(BaseModel):
    """Main audio language detection inference response model."""

    taskType: str = Field(
        default="audio-lang-detection",
        description="Task type identifier",
    )
    output: List[AudioLangDetectionOutput] = Field(
        ..., description="List of audio language detection results (one per audio input)"
    )
    config: Optional[AudioLangDetectionResponseConfig] = Field(
        None, description="Response configuration metadata"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)
