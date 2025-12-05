"""
NER Request Models

Pydantic models for NER inference requests, inspired by ULCA schemas
and mirroring the naming style used by ASR/TTS/NMT/OCR services.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class LanguageConfig(BaseModel):
    """Language configuration for NER."""

    sourceLanguage: str = Field(
        ..., description="Source language code (e.g., 'en', 'hi', 'ta')"
    )


class TextInput(BaseModel):
    """Text input for NER processing."""

    source: str = Field(..., description="Input text to analyze for entities")

    @model_validator(mode="after")
    def validate_source(self) -> "TextInput":
        if not self.source or not self.source.strip():
            raise ValueError("Source text cannot be empty")
        return self


class NerInferenceConfig(BaseModel):
    """Configuration for NER inference."""

    serviceId: str = Field(
        ..., description="Identifier for NER service/model (e.g., Dhruva NER)"
    )
    language: LanguageConfig = Field(..., description="Language configuration")


class NerInferenceRequest(BaseModel):
    """Main NER inference request model."""

    input: List[TextInput] = Field(
        ..., description="List of text inputs to process", min_items=1
    )
    config: NerInferenceConfig = Field(
        ..., description="Configuration for NER inference"
    )
    controlConfig: Optional[Dict[str, Any]] = Field(
        None, description="Additional control parameters (reserved for future use)"
    )

    @model_validator(mode="after")
    def validate_input(self) -> "NerInferenceRequest":
        if not self.input:
            raise ValueError("At least one text input is required")
        return self

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)



