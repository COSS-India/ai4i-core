"""NMT (Neural Machine Translation) service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TextInput(BaseModel):
    """Input for text-based NMT task."""

    source: str = Field(..., description="Text to translate")


class LanguagePair(BaseModel):
    """Language pair configuration for NMT."""

    source_language: str = Field(..., description="Source language code (e.g., 'en')")
    target_language: str = Field(..., description="Target language code (e.g., 'hi')")
    source_script_code: Optional[str] = Field(None, description="Source script code (e.g., 'Latn')")
    target_script_code: Optional[str] = Field(None, description="Target script code (e.g., 'Deva')")


class NMTConfig(BaseModel):
    """Configuration for NMT inference."""

    service_id: Optional[str] = Field(None, description="Service ID (optional, resolved by SMR)")
    language: LanguagePair = Field(..., description="Source and target language pair")
    context: Optional[str] = Field(None, description="Optional context for context-aware translation")


class NMTInferenceRequest(BaseModel):
    """Request for NMT inference."""

    input: List[TextInput] = Field(..., min_items=1, max_items=90, description="Text inputs to translate")
    config: NMTConfig = Field(..., description="NMT configuration")


class TranslationOutput(BaseModel):
    """Output from NMT inference."""

    source: str = Field(..., description="Original source text")
    target: str = Field(..., description="Translated target text")


class NMTInferenceResponse(BaseModel):
    """Response from NMT inference."""

    output: List[TranslationOutput] = Field(..., description="Translation results")
    smr_response: Optional[Dict[str, Any]] = Field(None, description="Smart Model Router metadata")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
