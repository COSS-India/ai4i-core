"""
Speaker Diarization Request & Response Models

Pydantic models for speaker diarization inference requests and responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


# -- Request models --


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


# -- Response models --


class Segment(BaseModel):
    """A single speaker segment in the audio."""

    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    duration: float = Field(..., description="Duration in seconds")
    speaker: str = Field(..., description="Speaker identifier (e.g., SPEAKER_00)")

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class SpeakerDiarizationOutput(BaseModel):
    """Output for a single audio input."""

    total_segments: int = Field(..., description="Total number of segments")
    num_speakers: int = Field(..., description="Number of speakers detected")
    speakers: List[str] = Field(..., description="List of speaker identifiers")
    segments: List[Segment] = Field(..., description="List of speaker segments")

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class SpeakerDiarizationResponseConfig(BaseModel):
    """Response configuration metadata."""

    serviceId: str = Field(..., description="Service identifier")
    language: Optional[str] = Field(None, description="Language code (if applicable)")

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class SpeakerDiarizationInferenceResponse(BaseModel):
    """Main speaker diarization inference response model."""

    taskType: str = Field(
        default="speaker-diarization",
        description="Task type identifier",
    )
    output: List[SpeakerDiarizationOutput] = Field(
        ..., description="List of speaker diarization results (one per audio input)"
    )
    config: Optional[SpeakerDiarizationResponseConfig] = Field(
        None, description="Response configuration metadata"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)
