"""Transliteration service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TextInput(BaseModel):
    """Input for transliteration task."""

    source: str = Field(..., description="Text to transliterate")


class TransliterationLanguagePair(BaseModel):
    """Language pair configuration for transliteration."""

    source_language: str = Field(..., description="Source language code")
    target_language: str = Field(..., description="Target language code")
    source_script_code: str = Field(..., description="Source script code")
    target_script_code: str = Field(..., description="Target script code")


class TransliterationConfig(BaseModel):
    """Configuration for transliteration inference."""

    service_id: str = Field(..., description="Service ID (required)")
    language: TransliterationLanguagePair = Field(..., description="Source and target language pair")
    preserve_case: Optional[bool] = Field(True, description="Preserve case in transliteration")


class TransliterationInferenceRequest(BaseModel):
    """Request for transliteration inference."""

    input: List[TextInput] = Field(
        ..., min_items=1, max_items=100, description="Text inputs to transliterate"
    )
    config: TransliterationConfig = Field(..., description="Transliteration configuration")


class TransliterationOutput(BaseModel):
    """Output from transliteration inference."""

    source: str = Field(..., description="Original source text")
    target: str = Field(..., description="Transliterated target text")


class TransliterationInferenceResponse(BaseModel):
    """Response from transliteration inference."""

    output: List[TransliterationOutput] = Field(..., description="Transliteration results")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
