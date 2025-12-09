"""
Audio Language Detection Response Models

Pydantic models for audio language detection inference responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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

