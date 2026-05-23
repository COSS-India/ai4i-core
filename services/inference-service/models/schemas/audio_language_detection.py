"""Audio Language Detection service request/response schemas."""

from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class AudioInput(BaseModel):
    """Input for audio-based language detection task."""

    model_config = ConfigDict(populate_by_name=True)

    audio_content: Optional[str] = Field(
        None, alias="audioContent", description="Base64 encoded audio data"
    )
    audio_uri: Optional[str] = Field(
        None, alias="audioUri", description="HTTP URL to audio file"
    )


class AudioLanguageDetectionConfig(BaseModel):
    """Configuration for audio language detection inference."""

    model_config = ConfigDict(populate_by_name=True)

    service_id: Optional[str] = Field(
        None, alias="serviceId", description="Service ID (optional, uses default if omitted)"
    )


class AudioLanguageDetectionInferenceRequest(BaseModel):
    """Request for audio language detection inference."""

    audio: List[AudioInput] = Field(
        ..., description="Audio inputs for language detection"
    )
    config: AudioLanguageDetectionConfig = Field(
        ..., description="Audio language detection configuration"
    )


class AllScores(BaseModel):
    """Full score breakdown returned by the Triton ALD model."""

    predicted_language: str = Field(
        ..., description="Top predicted language (e.g. 'ms: Malay')"
    )
    confidence: float = Field(
        ..., description="Confidence of top prediction (0-1)"
    )
    top_scores: List[float] = Field(
        default_factory=list, description="Confidence scores for top-N languages"
    )


class AudioLanguageDetectionOutput(BaseModel):
    """Output for a single audio item from language detection inference."""

    language_code: str = Field(
        ..., description="Detected language (e.g. 'ms: Malay')"
    )
    confidence: float = Field(
        ..., description="Detection confidence (0-1)"
    )
    all_scores: Optional[AllScores] = Field(
        None, description="Full score breakdown from the model"
    )


class AudioLanguageDetectionInferenceResponse(BaseModel):
    """Response from audio language detection inference."""

    output: List[AudioLanguageDetectionOutput] = Field(
        ..., description="Audio language detection results"
    )
