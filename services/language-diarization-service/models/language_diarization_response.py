"""
Language Diarization Response Models

Pydantic models for language diarization inference responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LanguageSegment(BaseModel):
    """A single language segment in the audio."""

    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    duration: float = Field(..., description="Duration in seconds")
    language: str = Field(..., description="Language code with name (e.g., 'hi: Hindi')")
    confidence: float = Field(..., description="Confidence score for the language detection")

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class LanguageDiarizationOutput(BaseModel):
    """Output for a single audio input."""

    total_segments: int = Field(..., description="Total number of segments")
    segments: List[LanguageSegment] = Field(..., description="List of language segments")
    target_language: str = Field(..., description="Target language code (empty string for all languages)")

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class LanguageDiarizationResponseConfig(BaseModel):
    """Response configuration metadata."""

    serviceId: str = Field(..., description="Service identifier")

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
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
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)

