"""
Speaker Diarization Request Models

Pydantic models for speaker diarization inference requests.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


class ControlConfig(BaseModel):
    """Control configuration for speaker diarization."""

    dataTracking: Optional[bool] = Field(
        True, description="Whether to enable data tracking"
    )


class SpeakerDiarizationConfig(BaseModel):
    """Configuration for speaker diarization inference."""

    serviceId: str = Field(
        ...,
        description="Identifier for speaker diarization service/model",
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


class SpeakerDiarizationInferenceRequest(BaseModel):
    """Main speaker diarization inference request model."""

    controlConfig: Optional[ControlConfig] = Field(
        None, description="Control configuration parameters"
    )
    config: SpeakerDiarizationConfig = Field(
        ..., description="Configuration for speaker diarization inference"
    )
    audio: List[AudioInput] = Field(
        ..., description="List of audio inputs to process", min_items=1
    )

    @model_validator(mode="after")
    def validate_audio_list(self) -> "SpeakerDiarizationInferenceRequest":
        """Ensure at least one audio input is provided."""
        if not self.audio:
            raise ValueError("At least one audio input is required")
        return self

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)

