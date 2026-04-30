"""
NER Request Models

Pydantic models for NER inference requests, inspired by ULCA schemas
and mirroring the naming style used by ASR/TTS/NMT/OCR services.
"""

from enum import Enum
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
        ..., description="Identifier for NER service/model"
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


"""
NER Response Models

Pydantic models for NER inference responses, mirroring the style used
by other services while keeping a ULCA-like structure.
"""


class TaskType(str, Enum):
    NER = "ner"


class NerTokenPrediction(BaseModel):
    """Token-level NER prediction."""

    token: Optional[str] = Field(None, description="Token text")
    tag: str = Field(..., description="NER tag (e.g., PERSON, ORG, O)")
    tokenIndex: Optional[int] = Field(
        None, description="Index of token within the input text"
    )
    tokenStartIndex: int = Field(
        ..., description="Character start index of token in the input text"
    )
    tokenEndIndex: int = Field(
        ..., description="Character end index of token in the input text"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class NerPrediction(BaseModel):
    """NER prediction for a single input text."""

    source: Optional[str] = Field(None, description="Original source text")
    nerPrediction: List[NerTokenPrediction] = Field(
        ..., description="List of token-level predictions"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class NerInferenceResponse(BaseModel):
    """Main NER inference response model."""

    taskType: TaskType = Field(
        default=TaskType.NER, description="Type of task (always 'ner')"
    )
    output: List[NerPrediction] = Field(
        ..., description="List of NER predictions (one per input text)"
    )
    config: Optional[Dict[str, Any]] = Field(
        None, description="Response configuration metadata (reserved for future use)"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)
