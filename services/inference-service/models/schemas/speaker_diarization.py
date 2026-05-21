"""Speaker Diarization service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AudioInput(BaseModel):
    """Input for audio-based speaker diarization task."""

    audio_content: Optional[str] = Field(None, description="Base64 encoded audio data")
    audio_uri: Optional[str] = Field(None, description="HTTP URL to audio file")


class SpeakerDiarizationConfig(BaseModel):
    """Configuration for speaker diarization inference."""

    service_id: str = Field(..., description="Service ID (required)")
    num_speakers: Optional[int] = Field(None, description="Expected number of speakers")


class SpeakerDiarizationInferenceRequest(BaseModel):
    """Request for speaker diarization inference."""

    audio: List[AudioInput] = Field(..., min_items=1, description="Audio inputs for speaker diarization")
    config: SpeakerDiarizationConfig = Field(..., description="Speaker diarization configuration")


class SpeakerSegment(BaseModel):
    """Speaker segment with timeline."""

    start_time_ms: float = Field(..., description="Segment start time in milliseconds")
    end_time_ms: float = Field(..., description="Segment end time in milliseconds")
    speaker_id: str = Field(..., description="Speaker identifier (e.g., 'Speaker_1')")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")


class SpeakerSegmentGroup(BaseModel):
    """Grouped speaker segments by speaker."""

    speaker_id: str = Field(..., description="Speaker identifier")
    segments: List[SpeakerSegment] = Field(..., description="All segments for this speaker")
    total_duration_ms: float = Field(..., description="Total speaking time for this speaker")


class SpeakerDiarizationOutput(BaseModel):
    """Output from speaker diarization inference."""

    segments: List[SpeakerSegment] = Field(..., description="All speaker segments with timing")
    speaker_groups: List[SpeakerSegmentGroup] = Field(..., description="Segments grouped by speaker")
    duration_ms: float = Field(..., description="Total audio duration in milliseconds")


class SpeakerDiarizationInferenceResponse(BaseModel):
    """Response from speaker diarization inference."""

    output: List[SpeakerDiarizationOutput] = Field(..., description="Speaker diarization results")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
