"""
LLM Request and Response Models

Pydantic models for LLM inference requests and responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class TextInput(BaseModel):
    """Text input for LLM."""
    source: str = Field(..., description="Input text to process")

    @field_validator("source")
    @classmethod
    def validate_source_text(cls, v):
        if not v or not v.strip():
            raise ValueError('Source text cannot be empty')
        if len(v) > 50000:
            raise ValueError('Source text cannot exceed 50000 characters')
        return v.strip()


class LLMInferenceConfig(BaseModel):
    """LLM inference configuration."""
    serviceId: str = Field(..., description="Identifier for LLM service/model")
    inputLanguage: Optional[str] = Field(None, description="Input language code (e.g., 'en', 'hi')")
    outputLanguage: Optional[str] = Field(None, description="Output language code")

    @field_validator("serviceId")
    @classmethod
    def validate_service_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Service ID cannot be empty')
        return v.strip()

    @field_validator("inputLanguage", "outputLanguage")
    @classmethod
    def validate_language_codes(cls, v):
        if v is not None and (len(v) < 2 or len(v) > 3):
            raise ValueError('Language codes must be 2-3 characters')
        return v


class LLMInferenceRequest(BaseModel):
    """LLM inference request."""
    input: List[TextInput] = Field(..., description="List of text inputs to process")
    config: LLMInferenceConfig = Field(..., description="Configuration for inference")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")

    @field_validator("input")
    @classmethod
    def validate_input_list(cls, v):
        if not v:
            raise ValueError('At least one text input is required')
        if len(v) > 100:
            raise ValueError('Maximum 100 text inputs allowed per request')
        return v

    def dict(self, **kwargs):
        """Override dict to exclude None values."""
        return super().model_dump(exclude_none=True, **kwargs)


class LLMOutput(BaseModel):
    """LLM output result."""
    source: str
    target: str

    def dict(self, **kwargs):
        """Override dict to exclude None values."""
        return super().model_dump(exclude_none=True, **kwargs)


class LLMInferenceResponse(BaseModel):
    """LLM inference response."""

    output: List[LLMOutput]
    # Populated for pay-per-use token accounting; never serialized to API clients.
    raw_response: Dict[str, Any] = Field(default_factory=dict, exclude=True)

    def dict(self, **kwargs):
        """Override dict to exclude None values."""
        return super().model_dump(exclude_none=True, **kwargs)
