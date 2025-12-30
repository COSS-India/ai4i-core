"""
Speaker Diarization Response Models

Pydantic models for speaker diarization inference responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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

