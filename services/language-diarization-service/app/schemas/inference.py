"""
Language Diarization Request & Response Models

Pydantic models for language diarization inference requests and responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


# -- Request models -----------------------------------------------------------


class ControlConfig(BaseModel):
    """Control configuration for language diarization."""

    dataTracking: Optional[bool] = Field(
        True, description="Whether to enable data tracking"
    )


class LanguageDiarizationConfig(BaseModel):
    """Configuration for language diarization inference."""

    serviceId: str = Field(
        ...,
        description="Identifier for language diarization service/model",
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


class LanguageDiarizationInferenceRequest(BaseModel):
    """Main language diarization inference request model."""

    controlConfig: Optional[ControlConfig] = Field(
        None, description="Control configuration parameters"
    )
    config: LanguageDiarizationConfig = Field(
        ..., description="Configuration for language diarization inference"
    )
    audio: List[AudioInput] = Field(
        ..., description="List of audio inputs to process", min_items=1
    )

    @model_validator(mode="after")
    def validate_audio_list(self) -> "LanguageDiarizationInferenceRequest":
        """Ensure at least one audio input is provided."""
        if not self.audio:
            raise ValueError("At least one audio input is required")
        return self

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


# -- Response models ----------------------------------------------------------


class LanguageSegment(BaseModel):
    """A single language segment in the audio."""

    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    duration: float = Field(..., description="Duration in seconds")
    language: str = Field(..., description="Language code with name (e.g., 'hi: Hindi')")
    confidence: float = Field(..., description="Confidence score for the language detection")

    def dict(self, **kwargs):  # type: ignore[override]
        return super().dict(exclude_none=True, **kwargs)


class LanguageDiarizationOutput(BaseModel):
    """Output for a single audio input."""

    total_segments: int = Field(..., description="Total number of segments")
    segments: List[LanguageSegment] = Field(..., description="List of language segments")
    target_language: str = Field(..., description="Target language code (empty string for all languages)")

    def dict(self, **kwargs):  # type: ignore[override]
        return super().dict(exclude_none=True, **kwargs)


class LanguageDiarizationResponseConfig(BaseModel):
    """Response configuration metadata."""

    serviceId: str = Field(..., description="Service identifier")

    def dict(self, **kwargs):  # type: ignore[override]
        return super().dict(exclude_none=True, **kwargs)


class LanguageDiarizationInferenceResponse(BaseModel):
    """Main language diarization inference response model."""

    taskType: str = Field(
        default="language-diarization",
        description="Task type identifier",
    )
    output: List[LanguageDiarizationOutput] = Field(
        ..., description="List of language diarization results (one per audio input)"
    )
    config: Optional[LanguageDiarizationResponseConfig] = Field(
        None, description="Response configuration metadata"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        return super().dict(exclude_none=True, **kwargs)
