"""NER (Named Entity Recognition) service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TextInput(BaseModel):
    """Input for text-based NER task."""

    source: str = Field(..., description="Text to process for entity recognition")


class NERLanguageConfig(BaseModel):
    """Language configuration for NER."""

    source_language: str = Field(
        ...,
        alias="sourceLanguage",
        description="Language code (e.g., 'hi', 'ta') — IndicNER supports Indian languages",
    )

    model_config = {"populate_by_name": True}


class NERConfig(BaseModel):
    """Configuration for NER inference."""

    service_id: Optional[str] = Field(None, alias="serviceId", description="Service ID")
    language: NERLanguageConfig = Field(..., description="Language configuration")

    model_config = {"populate_by_name": True}

    @property
    def resolved_service_id(self) -> Optional[str]:
        return self.service_id


class NERInferenceRequest(BaseModel):
    """Request for NER inference."""

    input: List[TextInput] = Field(..., min_items=1, description="Text inputs for NER")
    config: NERConfig = Field(..., description="NER configuration")


class Token(BaseModel):
    """Named entity token with classification."""

    text: str = Field(..., description="Token text")
    entity_type: str = Field(..., description="Entity type label")
    start_pos: int = Field(..., description="Character start position")
    end_pos: int = Field(..., description="Character end position")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")


class NEROutput(BaseModel):
    """Output from NER inference."""

    source: str = Field(..., description="Original input text")
    tokens: List[Token] = Field(..., description="Recognized entities and tokens")


class NERInferenceResponse(BaseModel):
    """Response from NER inference."""

    output: List[NEROutput] = Field(..., description="NER results")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
