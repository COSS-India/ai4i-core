"""Language Detection service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TextInput(BaseModel):
    """Input for language detection task."""

    source: str = Field(..., description="Text to detect language for")


class LanguageDetectionConfig(BaseModel):
    """Configuration for language detection inference."""

    service_id: Optional[str] = Field(None, alias="serviceId", description="Service ID")
    return_all_scores: Optional[bool] = Field(False, description="Return scores for all languages")

    model_config = {"populate_by_name": True}


class LanguageDetectionInferenceRequest(BaseModel):
    """Request for language detection inference."""

    input: List[TextInput] = Field(..., min_length=1, description="Text inputs for language detection")
    config: LanguageDetectionConfig = Field(..., description="Language detection configuration")


class LanguagePrediction(BaseModel):
    """Language prediction with confidence score."""

    language_code: str = Field(..., description="ISO 639-1 language code (e.g., 'en')")
    language: str = Field(..., description="Language name (e.g., 'English')")
    script_code: Optional[str] = Field(None, description="Script code (e.g., 'Latn')")
    confidence: float = Field(..., description="Confidence score (0-1)")


class LanguageDetectionOutput(BaseModel):
    """Output from language detection inference."""

    primary_language: LanguagePrediction = Field(..., description="Primary detected language")
    all_scores: Optional[List[LanguagePrediction]] = Field(
        None, description="All language predictions if requested"
    )


class LanguageDetectionInferenceResponse(BaseModel):
    """Response from language detection inference."""

    output: List[LanguageDetectionOutput] = Field(..., description="Language detection results")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
